# -*- coding: utf-8 -*-
"""hh-ИНВЕРСИЯ, шаг 5: пересчитать итог ПО БАЗЕ, а не по счётчику прогона.

Правило появилось после разбора 29.07: три отчётные цифры из пяти были завышены
в 1,7–2,5 раза, и все три одинаково — брались из потока разбора, а между потоком
и базой стоят дедупликация и чистка.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

STORE = r'C:\seostat\drop\drop-storage'
MASTER = os.path.join(STORE, 'master-base.sqlite')

print('=== ПРОВЕРКА ПО БАЗЕ (начало) ===', flush=True)
db = EDB.EnrichDB()
cx = db.cx

n_sig = cx.execute("SELECT COUNT(*) FROM signals WHERE source='hh-вакансия'").fetchone()[0]
n_inn = cx.execute("SELECT COUNT(DISTINCT inn) FROM signals WHERE source='hh-вакансия'").fetchone()[0]
print(f'сигналов source=hh-вакансия: {n_sig}, по ним ИНН: {n_inn}', flush=True)
print('по hotness:', cx.execute(
    "SELECT hotness, COUNT(*) FROM signals WHERE source='hh-вакансия' "
    'GROUP BY hotness ORDER BY 1 DESC').fetchall(), flush=True)
print('стадия hh_inversion в stage_log:', cx.execute(
    "SELECT COUNT(*) FROM stage_log WHERE stage='hh_inversion'").fetchone()[0], flush=True)
print('всего компаний в enrich.db сейчас:', cx.execute(
    'SELECT COUNT(*) FROM companies').fetchone()[0], flush=True)
print('из них is_competitor=1:', cx.execute(
    'SELECT COUNT(*) FROM companies WHERE is_competitor=1').fetchone()[0], flush=True)

инны = [r[0] for r in cx.execute(
    "SELECT DISTINCT inn FROM signals WHERE source='hh-вакансия'")]
mcx = sqlite3.connect(f'file:{MASTER}?mode=ro', uri=True)
в_мастере = set()
for i in range(0, len(инны), 400):
    ч = инны[i:i + 400]
    в_мастере |= {str(r[0]) for r in mcx.execute(
        'SELECT inn FROM master WHERE inn IN (%s)' % ','.join('?' * len(ч)), ч)}
print(f'ИНН с hh-сигналом, которые ЕСТЬ в базе обзвона: {len(в_мастере)}', flush=True)
print(f'ИНН с hh-сигналом, которых в базе обзвона НЕТ: {len(инны) - len(в_мастере)}',
      flush=True)

# сколько из них были в enrich.db ДО сегодняшнего прогона: у старых компаний
# updated_at отличается от даты записи стадии — но честнее взять stage_log
нов = [r[0] for r in cx.execute(
    "SELECT inn FROM stage_log WHERE stage='hh_inversion'")]
print('компаний со стадией hh_inversion:', len(нов), flush=True)

# профиль записанного
print('--- ОКВЭД компаний с hh-сигналом (2 знака), топ 14 ---', flush=True)
q = ("SELECT substr(COALESCE(c.okved,''),1,2) k, COUNT(*) FROM companies c "
     "JOIN (SELECT DISTINCT inn FROM signals WHERE source='hh-вакансия') s "
     'ON s.inn=c.inn GROUP BY k ORDER BY 2 DESC LIMIT 14')
for k, n in cx.execute(q):
    print(f'   {k or "?"}: {n}')
print('--- регионы, топ 12 ---', flush=True)
q = ("SELECT COALESCE(c.region,'?') k, COUNT(*) FROM companies c "
     "JOIN (SELECT DISTINCT inn FROM signals WHERE source='hh-вакансия') s "
     'ON s.inn=c.inn GROUP BY k ORDER BY 2 DESC LIMIT 12')
for k, n in cx.execute(q):
    print(f'   {k}: {n}')

# выручка по тем, кто есть в базе обзвона
рев = []
for i in range(0, len(инны), 400):
    ч = инны[i:i + 400]
    рев += [r[0] for r in mcx.execute(
        'SELECT revenue_rub FROM master WHERE inn IN (%s) AND revenue_rub IS NOT NULL'
        % ','.join('?' * len(ч)), ч) if r[0]]
рев = sorted(x for x in рев if isinstance(x, (int, float)) and x > 0)
if рев:
    print(f'выручка известна у {len(рев)}: медиана {рев[len(рев)//2]/1e6:.0f} млн ₽, '
          f'свыше 1 млрд {sum(1 for x in рев if x >= 1e9)}, '
          f'свыше 100 млн {sum(1 for x in рев if x >= 1e8)}', flush=True)
mcx.close()

print('--- 8 СВЕЖИХ ЗАПИСЕЙ ГЛАЗАМИ ---', flush=True)
for inn, what, url, hot in cx.execute(
        "SELECT inn, what, source_url, hotness FROM signals WHERE source='hh-вакансия' "
        'ORDER BY RANDOM() LIMIT 8'):
    nm = (cx.execute('SELECT name FROM companies WHERE inn=?', (inn,)).fetchone()
          or [''])[0]
    print(f'  {inn} h{hot} {(nm or "")[:44]}')
    print(f'     {what[:150]}')
    print(f'     {url}')
print('=== ПРОВЕРКА ПО БАЗЕ (конец) ===', flush=True)
print(f'ИТОГ: сигналов {n_sig}, компаний с сигналом {n_inn}, '
      f'в базе обзвона {len(в_мастере)}, вне её {len(инны) - len(в_мастере)}', flush=True)
