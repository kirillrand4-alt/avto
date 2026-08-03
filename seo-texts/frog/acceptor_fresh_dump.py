# -*- coding: utf-8 -*-
"""Свежий срез поисковых данных под пересчёт базы акцепторов (гост-посты).

Запуск на сервере:
    cd C:\\seostat
    .\\.venv\\Scripts\\python.exe drop\\drop-storage\\acceptor_fresh_dump.py
Только чтение БД (mode=ro). Результат — CSV в C:\\seostat\\drop\\drop-storage\\:
  fresh-sites.csv   — сайты панели + фактическая свежесть данных по каждому
  fresh-page.csv    — Источник;Сайт;URL;Клики;Показы;CTR;Позиция (окно 35 дн,
                      формат = экспорт all_sites_page, вход acceptor_value)
  fresh-query.csv   — то же на уровне URL×запрос (для анкоров), показы>=10
  fresh-device.csv  — URL×устройство (уточнение бот-фильтра), показы>=30
  fresh-index.csv   — последний снапшот индекса Яндекса по каждому сайту
  fresh-meta.json   — окно дат и максимальные даты по источникам
"""
import csv, datetime, json, os, sqlite3

DB = os.environ.get('SEOSTAT_DB', r'C:\seostat\data\seo.db')
OUT = os.environ.get('SEOSTAT_OUT', r'C:\seostat\drop\drop-storage')
DAYS = int(os.environ.get('FRESH_DAYS', '35'))
SRC_LABEL = {'gsc': 'Google', 'yandex_webmaster': 'Яндекс'}

os.makedirs(OUT, exist_ok=True)
con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
con.row_factory = sqlite3.Row

end = datetime.date.today() - datetime.timedelta(days=1)
start = end - datetime.timedelta(days=DAYS - 1)
S, E = start.isoformat(), end.isoformat()


def w(name, hdr, rows):
    with open(os.path.join(OUT, name), 'w', newline='', encoding='utf-8-sig') as f:
        c = csv.writer(f, delimiter=';'); c.writerow(hdr); c.writerows(rows)
    print(f'  {name}: {len(rows)} строк')


# --- сайты и свежесть ---
sites = con.execute(
    "SELECT s.id, so.code AS source, s.property_uri, s.enabled,"
    " (SELECT MAX(date) FROM page_metric_daily p WHERE p.site_id=s.id) AS max_page_date,"
    " (SELECT MAX(date) FROM visit v WHERE v.site_id=s.id) AS max_visit_date"
    " FROM site s JOIN source so ON so.id=s.source_id ORDER BY so.code, s.id").fetchall()
w('fresh-sites.csv',
  ['site_id', 'источник', 'property_uri', 'вкл', 'посл_дата_страниц', 'посл_дата_визитов'],
  [[r['id'], r['source'], r['property_uri'], r['enabled'],
    r['max_page_date'] or '', r['max_visit_date'] or ''] for r in sites])
for r in sites:
    print(f"    site {r['id']:>3} {r['source']:<16} {r['property_uri'][:50]:<50}"
          f" стр:{r['max_page_date'] or '-'} виз:{r['max_visit_date'] or '-'}")

# --- страницы: агрегат за окно, формат all_sites_page ---
rows = con.execute(
    "SELECT so.code AS src, s.property_uri AS site, pg.url AS url,"
    " SUM(m.clicks) AS clicks, SUM(m.impressions) AS shows,"
    " COALESCE(SUM(m.position*m.impressions)*1.0/NULLIF(SUM(m.impressions),0),"
    "          AVG(m.position)) AS pos"
    " FROM page_metric_daily m"
    " JOIN site s ON s.id=m.site_id JOIN source so ON so.id=s.source_id"
    " JOIN page pg ON pg.id=m.page_id"
    " WHERE m.date>=? AND m.date<=? AND so.code IN ('gsc','yandex_webmaster')"
    " GROUP BY m.site_id, m.page_id", (S, E)).fetchall()
w('fresh-page.csv', ['Источник', 'Сайт', 'URL', 'Клики', 'Показы', 'CTR %', 'Позиция'],
  [[SRC_LABEL.get(r['src'], r['src']), r['site'], r['url'], r['clicks'] or 0, r['shows'] or 0,
    round((r['clicks'] or 0) * 100.0 / r['shows'], 2) if r['shows'] else 0,
    round(r['pos'], 2) if r['pos'] is not None else ''] for r in rows])

# --- запросы: URL×запрос за окно (анкор-профиль кандидатов) ---
rows = con.execute(
    "SELECT so.code AS src, s.property_uri AS site, pg.url AS url, q.text AS query,"
    " SUM(m.clicks) AS clicks, SUM(m.impressions) AS shows,"
    " COALESCE(SUM(m.position*m.impressions)*1.0/NULLIF(SUM(m.impressions),0),"
    "          AVG(m.position)) AS pos"
    " FROM query_metric_daily m"
    " JOIN site s ON s.id=m.site_id JOIN source so ON so.id=s.source_id"
    " JOIN query q ON q.id=m.query_id"
    " LEFT JOIN page pg ON pg.id=m.page_id"
    " WHERE m.date>=? AND m.date<=? AND so.code IN ('gsc','yandex_webmaster')"
    " GROUP BY m.site_id, m.page_id, m.query_id"
    " HAVING SUM(m.impressions)>=10"
    " ORDER BY SUM(m.clicks) DESC, SUM(m.impressions) DESC LIMIT 400000", (S, E)).fetchall()
w('fresh-query.csv', ['Источник', 'Сайт', 'URL', 'Запрос', 'Клики', 'Показы', 'Позиция'],
  [[SRC_LABEL.get(r['src'], r['src']), r['site'], r['url'] or '', r['query'],
    r['clicks'] or 0, r['shows'] or 0,
    round(r['pos'], 2) if r['pos'] is not None else ''] for r in rows])

# --- устройства: URL×device (бот-фильтр) ---
rows = con.execute(
    "SELECT so.code AS src, s.property_uri AS site, pg.url AS url, m.device AS device,"
    " SUM(m.clicks) AS clicks, SUM(m.impressions) AS shows,"
    " COALESCE(SUM(m.position*m.impressions)*1.0/NULLIF(SUM(m.impressions),0),"
    "          AVG(m.position)) AS pos"
    " FROM device_metric_daily m"
    " JOIN site s ON s.id=m.site_id JOIN source so ON so.id=s.source_id"
    " JOIN page pg ON pg.id=m.page_id"
    " WHERE m.date>=? AND m.date<=?"
    " GROUP BY m.site_id, m.page_id, m.device HAVING SUM(m.impressions)>=30", (S, E)).fetchall()
w('fresh-device.csv', ['Источник', 'Сайт', 'URL', 'Устройство', 'Клики', 'Показы', 'Позиция'],
  [[SRC_LABEL.get(r['src'], r['src']), r['site'], r['url'], r['device'],
    r['clicks'] or 0, r['shows'] or 0,
    round(r['pos'], 2) if r['pos'] is not None else ''] for r in rows])

# --- индекс Яндекса: последний снапшот каждого сайта ---
rows = con.execute(
    "SELECT s.property_uri AS site, i.captured_on AS captured_on, i.normalized_url AS url"
    " FROM indexed_url_snapshot i JOIN site s ON s.id=i.site_id"
    " WHERE i.captured_on=(SELECT MAX(captured_on) FROM indexed_url_snapshot x"
    "                      WHERE x.site_id=i.site_id)").fetchall()
w('fresh-index.csv', ['Сайт', 'Дата_снапшота', 'URL'],
  [[r['site'], r['captured_on'], r['url']] for r in rows])

meta = dict(window_start=S, window_end=E, days=DAYS,
            generated=datetime.datetime.now().isoformat(timespec='seconds'),
            max_dates={r['source'] + ':' + r['property_uri']: r['max_page_date']
                       for r in sites if r['max_page_date']})
json.dump(meta, open(os.path.join(OUT, 'fresh-meta.json'), 'w'), ensure_ascii=False, indent=1)
print(f'\nготово. Окно {S}..{E}. Файлы в {OUT}')
