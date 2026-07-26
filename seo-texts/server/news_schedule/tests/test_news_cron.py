# -*- coding: utf-8 -*-
"""Тесты прогона news_cron (#49-б, п.5): дедуп по seen_news, идемпотентность,
устойчивость к падению донора, метрики scan_runs. Провайдер и dadata замоканы
(в интернет не ходим; монкипатчим атрибуты news_scan — news_cron зовёт их через
NS.* именно для этого)."""
import news_cron
import news_scan
import no_rss
from conftest import FakeWeb, render_fixture


def _fake_llm(monkeypatch):
    """Мок провайдера/даданных: детерминированный «fable» без сети.
    Возвращает список вызовов extract — тесты меряют траты провайдера."""
    calls = []

    def fake_extract(title, source):
        calls.append(title)
        # «капекс» — если заголовок похож на стройку/деньги (та же роль, что fable)
        if any(w in title.lower() for w in ('цех', 'млрд', 'производств', 'завод')):
            company = ' '.join(title.split()[:2])
            return {'is_capex': True, 'company': company, 'event_type': 'расширение',
                    'what': title[:60], 'region': 'Тестовый регион', 'country': 'РФ',
                    'sum': '', 'hotness': 3}
        return {'is_capex': False}

    def fake_dadata(name, token):
        if not name:
            return None
        return {'inn': str(7700000000 + abs(hash(name)) % 10**9), 'okved': '25.62',
                'name': f'ООО «{name}»', 'region': 'Тестовая обл.', 'status': 'ACTIVE',
                'egrul_emails': [], 'confidence': 'high'}

    monkeypatch.setattr(news_scan, 'extract_event', fake_extract)
    monkeypatch.setattr(news_scan, 'dadata_suggest', fake_dadata)
    return calls


def _seed_donors(db):
    """Два донора: с объявленным RSS (дискавери news_scan) и без RSS (лестница)."""
    db.add_donor('rss-primer.ru', rss='https://rss-primer.ru/feed.xml',
                 rss_items=3, status='live')
    db.add_donor('vestnik-primer.ru', status='no-rss')


def _pages():
    return {
        'https://rss-primer.ru/feed.xml': render_fixture('rss.xml'),
        'https://vestnik-primer.ru/news': render_fixture('listing.html'),
    }


def test_run_polls_all_writes_signals_and_metrics(db, opts_factory, monkeypatch):
    calls = _fake_llm(monkeypatch)
    _seed_donors(db)
    summary = news_cron.run(opts_factory(), fetch=FakeWeb(_pages()))

    assert summary['donors_polled'] == 2 and summary['donors_ok'] == 2
    assert summary['errors'] == 0
    # RSS: 2 свежие ссылки (старая отсеяна); листинг: 3 (старьё/чужой хост отсеяны)
    assert summary['new_links'] == 5
    # капекс-предфильтр отсёк «погоду» ДО провайдера — fable её не видел
    assert summary['capex_candidates'] == 4
    assert len(calls) == 4
    assert not any('Погода' in t for t in calls)
    # каждый капекс дал сигнал с ИНН (мок dadata)
    assert summary['new_signals'] == 4
    assert db.cx.execute('SELECT COUNT(*) FROM signals').fetchone()[0] == 4
    # ссылки легли в seen_news (дедуп-память кросс-прогонная)
    assert db.cx.execute('SELECT COUNT(*) FROM seen_news').fetchone()[0] == 5
    # метрики прогона durable в scan_runs
    row = db.cx.execute('SELECT donors_polled, new_links, new_signals, errors '
                        'FROM scan_runs').fetchone()
    assert row == (2, 5, 4, 0)
    # безрss-донор запомнил рабочий способ
    pm = db.cx.execute("SELECT probe_method FROM donors WHERE domain='vestnik-primer.ru'"
                       ).fetchone()[0]
    assert pm == 'listing'
    # здоровье доноров обновлено
    ok = db.cx.execute("SELECT last_ok, last_new, COALESCE(fail_streak,0) FROM donors "
                       "WHERE domain='rss-primer.ru'").fetchone()
    assert ok[0] and ok[1] and ok[2] == 0


def test_second_run_is_idempotent(db, opts_factory, monkeypatch):
    calls = _fake_llm(monkeypatch)
    _seed_donors(db)
    news_cron.run(opts_factory(), fetch=FakeWeb(_pages()))
    n_calls_after_first = len(calls)
    sig_after_first = db.cx.execute('SELECT COUNT(*) FROM signals').fetchone()[0]

    # повторный прогон на тех же данных: всё уже в seen_news
    summary2 = news_cron.run(opts_factory(), fetch=FakeWeb(_pages()))
    assert summary2['new_links'] == 0
    assert summary2['new_signals'] == 0
    assert summary2['errors'] == 0
    # провайдер НЕ дёргался повторно (дедуп ДО извлечения — экономия fable)
    assert len(calls) == n_calls_after_first
    assert db.cx.execute('SELECT COUNT(*) FROM signals').fetchone()[0] == sig_after_first
    # оба прогона записаны в метрики
    assert db.cx.execute('SELECT COUNT(*) FROM scan_runs').fetchone()[0] == 2


def test_second_run_skips_ladder_for_memorized_method(db, opts_factory, monkeypatch):
    _fake_llm(monkeypatch)
    _seed_donors(db)
    news_cron.run(opts_factory(), fetch=FakeWeb(_pages()))
    fake2 = FakeWeb(_pages())
    news_cron.run(opts_factory(), fetch=fake2)
    # безrss-донор во втором прогоне идёт СРАЗУ запомненным способом
    assert fake2.count('vestnik-primer.ru/rss') == 0
    assert fake2.count('vestnik-primer.ru/sitemap') == 0


def test_donor_exception_does_not_kill_run(db, opts_factory, monkeypatch):
    calls = _fake_llm(monkeypatch)
    _seed_donors(db)

    def boom(db_, row, fetcher, days, max_articles=8):
        raise RuntimeError('донор упал')
    # падает ВЕСЬ опрос без-RSS донора — прогон обязан дожить и опросить остальных
    monkeypatch.setattr(no_rss, 'poll_donor', boom)

    summary = news_cron.run(opts_factory(), fetch=FakeWeb(_pages()))
    assert summary['errors'] == 1
    assert summary['donors_polled'] == 2 and summary['donors_ok'] == 1
    # RSS-донор отработал, его капекс дошёл до извлечения
    assert any('Северный' in t or 'Комбинат' in t for t in calls)
    # упавшему донору выросла полоса ошибок (метрика «мёртвых»)
    fs = db.cx.execute("SELECT fail_streak FROM donors WHERE domain='vestnik-primer.ru'"
                       ).fetchone()[0]
    assert fs == 1
    # ошибка попала в метрики прогона
    assert db.cx.execute('SELECT errors FROM scan_runs').fetchone()[0] == 1


def test_dry_run_polls_but_never_extracts(db, opts_factory, monkeypatch):
    calls = _fake_llm(monkeypatch)
    _seed_donors(db)
    summary = news_cron.run(opts_factory(dry_run=True), fetch=FakeWeb(_pages()))
    assert summary['new_links'] == 5
    assert summary['capex_candidates'] == 4
    assert summary['events'] == 0 and summary['new_signals'] == 0
    assert calls == []           # провайдер не тронут


def test_dead_donor_excluded_after_max_fail(db, opts_factory, monkeypatch):
    import schedule_db as SDB
    _fake_llm(monkeypatch)
    _seed_donors(db)
    for _ in range(10):
        SDB.donor_fail(db, 'vestnik-primer.ru')
    summary = news_cron.run(opts_factory(), fetch=FakeWeb(_pages()))
    # «мёртвый» донор (10 ошибок подряд) в прогон не попал — не жжём время на труп
    assert summary['donors_polled'] == 1
