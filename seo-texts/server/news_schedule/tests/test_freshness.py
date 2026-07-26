# -*- coding: utf-8 -*-
"""Тесты метрик свежести (#49-б, п.3): свежее 7/30 дней, молчащие и мёртвые
доноры, текстовая сводка."""
import freshness
import schedule_db as SDB


def _old_iso(days):
    return SDB.iso_ago(days)


def test_metrics_signal_freshness_windows(db):
    # свежий сигнал — обычным путём (updated_at = сейчас)
    db.add_signal('7700000001', source='test', what='новый цех', source_url='http://a/1')
    # старые — напрямую с датами записи 10 и 60 дней назад
    for inn, age in (('7700000002', 10), ('7700000003', 60)):
        db.cx.execute('INSERT INTO signals(inn,source,event_type,what,sum,source_url,'
                      'hotness,ts,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                      (inn, 'test', '', f'что-то {age}', '', 'http://a/x', 0, '', _old_iso(age)))
    db.cx.commit()
    m = freshness.metrics(db)
    assert m['signals_total'] == 3
    assert m['signals_7d'] == 1          # только сегодняшний
    assert m['signals_30d'] == 2         # сегодняшний + 10-дневный


def test_metrics_silent_and_dead_donors(db):
    db.add_donor('fresh-donor.ru', rss='https://fresh-donor.ru/rss', status='live')
    db.add_donor('silent-donor.ru', status='no-rss')
    db.add_donor('dead-donor.ru', status='no-rss')
    # свежий: давал новые ссылки только что
    SDB.donor_ok(db, 'fresh-donor.ru', new_links=3)
    # молчащий: последние новые ссылки — 45 дней назад
    db.cx.execute("UPDATE donors SET last_new=? WHERE domain='silent-donor.ru'",
                  (_old_iso(45),))
    db.cx.commit()
    # мёртвый: 6 ошибок подряд
    for _ in range(6):
        SDB.donor_fail(db, 'dead-donor.ru')

    m = freshness.metrics(db)
    assert m['donors_total'] == 3
    assert m['donors_rss'] == 1
    assert m['donors_dead'] == 1
    # молчащие: silent-donor (45д) — да; dead — исключён (он «мёртвый», не «молчащий»);
    # fresh — нет
    assert m['donors_silent'] == 1


def test_report_text_contains_key_numbers(db):
    db.add_signal('7700000009', source='test', what='запуск линии', source_url='http://b/1')
    SDB.record_run(db, donors_polled=7, donors_ok=6, new_links=12, new_signals=3,
                   errors=1, took_sec=42.5)
    txt = freshness.report(db)
    assert 'свежее 7д: 1' in txt
    assert 'доноров 7' in txt
    assert 'новых ссылок 12' in txt
    assert 'новых сигналов 3' in txt
    assert 'ошибок 1' in txt


def test_report_without_runs(db):
    assert 'прогонов ещё не было' in freshness.report(db)
