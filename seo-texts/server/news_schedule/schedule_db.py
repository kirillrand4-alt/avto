# -*- coding: utf-8 -*-
"""Схема-расширение enrich.db под РЕГУЛЯРНЫЙ news-скан (задача #49-б):
здоровье доноров + журнал прогонов scan_runs.

ЗАЧЕМ отдельный модуль, а не правка enrich_db.py: enrich_db — общая библиотека
всех конвейеров (news/mass/Meyer), и по правилам задачи мы пишем только в свой
каталог. Поэтому все дополнения схемы живут здесь и накатываются на УЖЕ открытую
EnrichDB тем же безопасным приёмом, что миграции в самой enrich_db.__init__
(ALTER TABLE под try/except: колонка уже есть → тихо едем дальше). Старому коду
новые колонки не мешают — он их не выбирает.

Новые колонки donors:
  probe_method — рабочий способ опроса донора БЕЗ RSS:
                 'rss-path' | 'sitemap' | 'listing' | 'none' (см. no_rss.py);
  probe_url    — конкретный рабочий URL (лента / карта сайта / раздел новостей);
  probed_at    — когда лестница пробовалась в последний раз (чтобы не гонять её
                 по «none»-донорам каждый день: сайт без раздела новостей не
                 отрастит его за сутки);
  fail_streak  — ошибок доступности ПОДРЯД (метрика «мёртвый донор»);
  last_ok      — последний УСПЕШНЫЙ опрос (даже если 0 новых ссылок);
  last_new     — последний раз, когда донор дал НОВЫЕ ссылки (метрика «молчащий»).

Новая таблица scan_runs — метрики каждого прогона news_cron (требование задачи:
ts, доноров опрошено, новых ссылок, новых сигналов, ошибок)."""
import time

DONOR_COLS = (
    ('probe_method', 'TEXT'),
    ('probe_url', 'TEXT'),
    ('probed_at', 'TEXT'),
    ('fail_streak', 'INTEGER DEFAULT 0'),
    ('last_ok', 'TEXT'),
    ('last_new', 'TEXT'),
)

_SCAN_RUNS = """
CREATE TABLE IF NOT EXISTS scan_runs(
  ts TEXT, donors_polled INTEGER, donors_ok INTEGER, new_links INTEGER,
  new_signals INTEGER, errors INTEGER, took_sec REAL, note TEXT);
"""

# Домены-«доноры», которые на деле — коллекторы самого news_scan: bump_donor пишет
# домен source_url КАЖДОГО события, включая посты ВК, вакансии hh и госзакупки.
# Лестница/RSS-опрос по ним бессмыслен (и шумит в метриках): их опрашивают
# собственные коллекторы news_scan (col_vk / col_hh / col_zakupki / col_google).
SKIP_DOMAINS = frozenset((
    'vk.com', 'm.vk.com', 'ok.ru', 't.me', 'hh.ru', 'news.google.com',
    'zakupki.gov.ru', 'yandex.ru', 'dzen.ru', 'youtube.com', 'rutube.ru',
))


def now_iso():
    """Тот же формат, что EnrichDB.now ('%Y-%m-%dT%H:%M:%S'): сравнение строк =
    сравнение времени, метрики свежести считаются одним SQL без парсинга дат."""
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def iso_ago(days):
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() - days * 86400))


def migrate(db):
    """Идемпотентная миграция: безопасно звать на каждом старте news_cron
    (и нужно — БД могла быть создана старым кодом без наших колонок)."""
    for col, typ in DONOR_COLS:
        try:
            db.cx.execute(f'ALTER TABLE donors ADD COLUMN {col} {typ}')
        except Exception:  # noqa: BLE001 — колонка уже существует, это норма
            pass
    db.cx.executescript(_SCAN_RUNS)
    db.cx.commit()


def record_run(db, donors_polled, donors_ok, new_links, new_signals, errors,
               took_sec, note=''):
    """Строка метрик прогона — durable в enrich.db (панель/отчёты читают отсюда)."""
    db.cx.execute(
        'INSERT INTO scan_runs(ts,donors_polled,donors_ok,new_links,new_signals,'
        'errors,took_sec,note) VALUES(?,?,?,?,?,?,?,?)',
        (now_iso(), int(donors_polled), int(donors_ok), int(new_links),
         int(new_signals), int(errors), round(float(took_sec), 1), str(note)[:200]))
    db.cx.commit()


def set_probe(db, domain, method, url):
    """Запомнить результат лестницы no_rss durable: следующий прогон идёт сразу
    рабочим способом, не тратя запросы (и вежливые паузы) на передискавери."""
    ts = now_iso()
    db.cx.execute(
        'UPDATE donors SET probe_method=?, probe_url=?, probed_at=?, updated_at=? '
        'WHERE domain=?', (method or '', url or '', ts, ts, domain))
    db.cx.commit()


def donor_ok(db, domain, new_links):
    """Успешный опрос: полоса ошибок обнуляется. Ноль новых ссылок — тоже успех
    (last_ok двигается, last_new — нет: по нему считаем «молчащих»)."""
    ts = now_iso()
    if int(new_links) > 0:
        db.cx.execute('UPDATE donors SET fail_streak=0, last_ok=?, last_new=?, '
                      'updated_at=? WHERE domain=?', (ts, ts, ts, domain))
    else:
        db.cx.execute('UPDATE donors SET fail_streak=0, last_ok=?, updated_at=? '
                      'WHERE domain=?', (ts, ts, domain))
    db.cx.commit()


def donor_fail(db, domain):
    """Ошибка доступности: +1 к полосе. Полоса >= max_fail → донора перестаём
    опрашивать (см. donors_to_poll) и показываем в метриках как «мёртвого»."""
    db.cx.execute('UPDATE donors SET fail_streak=COALESCE(fail_streak,0)+1, '
                  'updated_at=? WHERE domain=?', (now_iso(), domain))
    db.cx.commit()


def donors_to_poll(db, max_fail=10, none_retry_days=7, limit=0):
    """Кого опрашивать в этом прогоне. Пропускаем:
      - домены-коллекторы (SKIP_DOMAINS — их кроет сам news_scan);
      - «мёртвых» (fail_streak >= max_fail): не жечь время прогона на трупах;
        реанимация вручную — UPDATE donors SET fail_streak=0 WHERE domain=...;
      - «none»-доноров, лестница по которым гонялась недавно (< none_retry_days).
    Продуктивные (event_count) — первыми: если прогон оборвётся по таймауту,
    самое ценное уже будет собрано."""
    cutoff = iso_ago(none_retry_days)
    rows = db.cx.execute(
        'SELECT domain, rss, status, probe_method, probe_url, '
        '       COALESCE(fail_streak,0), COALESCE(probed_at,"") '
        'FROM donors ORDER BY event_count DESC').fetchall()
    out = []
    for domain, rss, status, pm, pu, streak, probed in rows:
        if domain in SKIP_DOMAINS or streak >= max_fail:
            continue
        if (pm or '') == 'none' and probed and probed >= cutoff and not (rss or ''):
            continue
        out.append({'domain': domain, 'rss': rss or '', 'status': status or '',
                    'probe_method': pm or '', 'probe_url': pu or '',
                    'fail_streak': streak})
        if limit and len(out) >= limit:
            break
    return out
