# -*- coding: utf-8 -*-
"""Отдать разобранные сайты P25 в enrich.db, иначе обход руководства их не увидит.

`leadership.py` берёт сайт ОДНИМ запросом: `SELECT site FROM companies`. Все
367 сайтов, что я сегодня разобрал и рассудил, лежат в `p25.db.company.sayt` —
для обхода руководства их всё равно что нет. Это та же дыра, что была с полем
уверенности: значение добыто, а прибор, которому оно нужно, смотрит в другое
место.

Лью ТОЛЬКО в пустую клетку и только те, что прошли разбор. Спорные-ничьи
(35 штук) НЕ лью: там мы не знаем ответа, и заливать «на всякий случай» —
это ровно то, за что сегодня уже пришлось откатываться.

Запуск: python p25_sayty_v_enrich.py [--apply]
"""
import io, json, os, re, sqlite3, sys, time
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

P25 = r'C:\seostat\data\p25.db'
ПРИГ = r'C:\seostat\drop\sayty_prigovory.jsonl'
ПОТОК = r'C:\seostat\drop\p25_sayty_v_enrich.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv

ничьи = set()
for стр in io.open(ПРИГ, encoding='utf-8', errors='replace'):
    try:
        з = json.loads(стр)
    except Exception:
        continue
    if з.get('otkat'):
        ничьи.discard(str(з.get('inn')))
    elif 'глаза' in str(з.get('prigovor', '')):
        ничьи.add(str(з.get('inn')))

db = EDB.EnrichDB()
поля = {r[1] for r in db.cx.execute('PRAGMA table_info(companies)')}
есть = {}
для_вставки = []
for и, с in db.cx.execute("SELECT inn, COALESCE(site,'') FROM companies"):
    есть[str(и)] = str(с).strip()

цб = sqlite3.connect(f'file:{P25}?mode=ro', uri=True)
стат = Counter()
лить = []
for и, с, ист in цб.execute("SELECT inn, COALESCE(sayt,''), "
                            "COALESCE(istochnik_sayta,'') FROM company"):
    и, с = str(и), str(с).strip().lower()
    if not с:
        стат['в карточке P25 сайта нет'] += 1
        continue
    if и in ничьи:
        стат['спор не решён — НЕ лью'] += 1
        continue
    если_есть = есть.get(и)
    if и not in есть:
        стат['ИНН нет в enrich.companies вовсе'] += 1
        для_вставки.append((и, с, ист))
        continue
    if если_есть:
        стат['в enrich уже стоит сайт' if если_есть.lower() == с
             else 'в enrich стоит ДРУГОЙ сайт — не трогаю'] += 1
        continue
    стат['ЛИТЬ: в enrich пусто'] += 1
    лить.append((и, с, ист))
цб.close()

for к, v in sorted(стат.items(), key=lambda x: -x[1]):
    print(f'{к:44} {v:5}')
print()
print(f'к заливу в enrich.companies.site {len(лить)}, '
      f'ИНН отсутствуют в enrich {len(для_вставки)}')

if not ПРИМЕНИТЬ:
    print('СУХОЙ ПРОГОН')
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
влито = 0
for и, с, ист in лить:
    db.cx.execute("UPDATE companies SET site=? WHERE inn=? AND COALESCE(site,'')=''",
                  (с, и))
    влито += db.cx.total_changes and 1 or 0
db.cx.commit()
с_сайтом = db.cx.execute("SELECT COUNT(*) FROM companies "
                         "WHERE COALESCE(site,'')<>''").fetchone()[0]
with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for и, с, ист in лить:
        ф.write(json.dumps({'inn': и, 'site': с, 'istochnik': ист, 'ts': ts},
                           ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())
print(f'влито строк                {len(лить):6}')
print(f'в enrich.companies с сайтом {с_сайтом:6}')
