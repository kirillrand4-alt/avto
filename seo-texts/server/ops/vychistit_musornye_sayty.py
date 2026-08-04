# -*- coding: utf-8 -*-
"""Вычистить домены-статику, которые я залил в карточки и в enrich.db.

Моя ошибка, не соседок: съём сайта с чеко брал ПЕРВУЮ ссылку страницы, не
попавшую в заслон, а первой там стоит `yastatic.net`. Заслон знал соцсети,
агрегаторов и госпорталы — и не знал CDN, счётчиков и шрифтов.

Чищу везде, где сам же и записал: карточки P25 и центробежки, `companies.site`
и `companies.site_checko`. Клетка возвращается в ПУСТОЕ состояние — это честнее,
чем оставить домен, который не открывает ни одного предприятия.
"""
import io, json, os, re, sqlite3, sys, time
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB
ХЛАМ = re.compile(
    r'yastatic|ya\.ru|yandex|gstatic|googleapis|google\.com|cloudflare|'
    r'jsdelivr|unpkg|bootstrapcdn|jquery|fontawesome|cdn\.|static\.|'
    r'w3\.org|schema\.org|gravatar|recaptcha', re.I)
ПОТОК = r'C:\seostat\drop\vychishcheno_musornyh_saytov.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
стат = Counter(); журнал = []
ts = time.strftime('%Y-%m-%dT%H:%M:%S')
for имя, путь in (('P25', r'C:\seostat\data\p25.db'),
                  ('центробежка', r'C:\seostat\data\centrifugal.db')):
    цб = sqlite3.connect(путь, timeout=30)
    поле = 'sayt' if 'sayt' in {r[1] for r in цб.execute('PRAGMA table_info(company)')} else 'site'
    цели = [(str(и), с) for и, с in цб.execute(
        f"SELECT inn, COALESCE({поле},'') FROM company WHERE COALESCE({поле},'')<>''")
        if ХЛАМ.search(str(с))]
    стат[f'{имя}: к очистке'] = len(цели)
    if ПРИМЕНИТЬ and цели:
        for и, с in цели:
            цб.execute(f"UPDATE company SET {поле}='' WHERE inn=?", (и,))
            журнал.append({'baza': имя, 'inn': и, 'bylo': с, 'ts': ts})
        цб.commit()
        стат[f'{имя}: с сайтом стало'] = цб.execute(
            f"SELECT COUNT(*) FROM company WHERE COALESCE({поле},'')<>''").fetchone()[0]
    цб.close()
db = EDB.EnrichDB()
for кол in ('site', 'site_checko'):
    try:
        цели = [(str(и), с) for и, с in db.cx.execute(
            f"SELECT inn, COALESCE({кол},'') FROM companies WHERE COALESCE({кол},'')<>''")
            if ХЛАМ.search(str(с))]
    except Exception:
        continue
    стат[f'enrich.{кол}: к очистке'] = len(цели)
    if ПРИМЕНИТЬ and цели:
        for и, с in цели:
            db.cx.execute(f"UPDATE companies SET {кол}='' WHERE inn=?", (и,))
            журнал.append({'baza': f'enrich.{кол}', 'inn': и, 'bylo': с, 'ts': ts})
        db.cx.commit()
if ПРИМЕНИТЬ and журнал:
    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in журнал:
            ф.write(json.dumps(з, ensure_ascii=False) + '\n')
        ф.flush(); os.fsync(ф.fileno())
for к, v in sorted(стат.items()):
    print(f'{к:34} {v:6}')
print('ОЧИЩЕНО СТРОК:', len(журнал) if ПРИМЕНИТЬ else 'сухой прогон')
