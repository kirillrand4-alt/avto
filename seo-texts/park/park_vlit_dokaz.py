# -*- coding: utf-8 -*-
"""Принимает журнал съёмки доказательств в park.db, чтобы панель показала снимки.

Съёмка идёт на сервере (`park_1s_dokaz.py`) и пишет `park_dokaz.jsonl` с fsync. Здесь
журнал переносится в таблицу `dokaz_snimok`, откуда сборка панели кладёт имя файла рядом
с фактом. Картинки лежат в статике панели, поэтому карточке хватает имени.

Имя журнала берётся из первого довода. Раньше оно было вшито в код — и это стоило тика:
свежий журнал приезжает с сервера под именем `PARK-DOKAZ-SNIMKI-1S.jsonl`, а приёмник читал
старый `park_dokaz.jsonl` и бодро печатал «принято 10 825», хотя не принял ни одной новой
строки. Таблица стояла на 10 679, пока на сервере лежало 12 355 — 1 676 снимков просто не
доезжали, и счётчик об этом молчал.

Запуск: python3 park_vlit_dokaz.py [журнал.jsonl]
"""
import json, os, sqlite3, sys

D = os.path.dirname(os.path.abspath(__file__))
ZHURNAL = sys.argv[1] if len(sys.argv) > 1 else 'park_dokaz.jsonl'
if not os.path.isabs(ZHURNAL):
    ZHURNAL = os.path.join(D, ZHURNAL)
if not os.path.exists(ZHURNAL):
    raise SystemExit('нет журнала: %s' % ZHURNAL)
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
c.execute("""create table if not exists dokaz_snimok(
    fakt_id integer primary key, inn text, url text, snimok text, verdikt text,
    inn_na_stranice integer, tip_na_stranice integer, znakov integer, ts text)""")
bylo = c.execute('select count(*) from dokaz_snimok').fetchone()[0]
n = 0
for ln in open(ZHURNAL, encoding='utf-8', errors='replace'):
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
stalo = q('select count(*) from dokaz_snimok')
print('журнал: %s' % os.path.basename(ZHURNAL))
print('строк со снимком принято: %d' % n)
print('  в таблице было %d, стало %d, ПРИБЫЛО %d' % (bylo, stalo, stalo - bylo))
print('  ИНН виден на странице .. %d' % q('select count(*) from dokaz_snimok where inn_na_stranice=1'))
print('  тип виден на странице .. %d' % q('select count(*) from dokaz_snimok where tip_na_stranice=1'))
p.close()
