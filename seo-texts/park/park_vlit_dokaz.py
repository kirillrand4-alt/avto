# -*- coding: utf-8 -*-
"""Принимает журнал съёмки доказательств в park.db, чтобы панель показала снимки.

Съёмка идёт на сервере (`park_1s_dokaz.py`) и пишет `park_dokaz.jsonl` с fsync. Здесь
журнал переносится в таблицу `dokaz_snimok`, откуда сборка панели кладёт имя файла рядом
с фактом. Картинки лежат в статике панели, поэтому карточке хватает имени.
"""
import json, os, sqlite3

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
c.execute("""create table if not exists dokaz_snimok(
    fakt_id integer primary key, inn text, url text, snimok text, verdikt text,
    inn_na_stranice integer, tip_na_stranice integer, znakov integer, ts text)""")
n = 0
for ln in open(os.path.join(D, 'park_dokaz.jsonl'), encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    x = json.loads(ln)
    if x.get('verdikt') != 'снимок сделан':
        continue
    c.execute("""insert or replace into dokaz_snimok(fakt_id, inn, url, snimok, verdikt,
                   inn_na_stranice, tip_na_stranice, znakov, ts)
                 values (?,?,?,?,?,?,?,?,?)""",
              (x['fakt_id'], x['inn'], x['url'], x['snimok'], x['verdikt'],
               1 if x.get('inn_na_stranice') else 0, 1 if x.get('tip_na_stranice') else 0,
               x.get('znakov'), x.get('ts')))
    n += 1
p.commit()
q = lambda s: c.execute(s).fetchone()[0]
print('снимков в журнале принято: %d' % n)
print('  всего в таблице ........ %d' % q('select count(*) from dokaz_snimok'))
print('  ИНН виден на странице .. %d' % q('select count(*) from dokaz_snimok where inn_na_stranice=1'))
print('  тип виден на странице .. %d' % q('select count(*) from dokaz_snimok where tip_na_stranice=1'))
p.close()
