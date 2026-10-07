# -*- coding: utf-8 -*-
"""Замер форматов дат в centro_sales.db. Ноль может быть правдой, а может быть сравнением
строки с пробелом против строки с 'T' — в ASCII пробел меньше 'T', и тогда любой свежий
час выглядит как «давно», то есть счётчик врёт нулём, не падая.
"""
import datetime
import os
import sqlite3
import sys

BAZA = r'C:\centro2\data\centro_sales.db'
c = sqlite3.connect(BAZA)
c.row_factory = sqlite3.Row
print('база: %s' % BAZA)

tabl = [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print('таблицы: %s' % ', '.join(tabl))

for t, pole in (('activity_log', 'created_at'),
                ('company_state', 'next_contact_at'),
                ('company_state', 'last_contact_at'),
                ('company_comment', 'created_at')):
    if t not in tabl:
        print('\n%s.%s: таблицы нет' % (t, pole))
        continue
    kol = [r[1] for r in c.execute('PRAGMA table_info(%s)' % t)]
    if pole not in kol:
        print('\n%s.%s: колонки нет. есть: %s' % (t, pole, ', '.join(kol)))
        continue
    vsego = c.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
    nepusto = c.execute(
        "SELECT COUNT(*) FROM %s WHERE %s IS NOT NULL AND %s<>''" % (t, pole, pole)
    ).fetchone()[0]
    obrazcy = [r[0] for r in c.execute(
        "SELECT %s FROM %s WHERE %s IS NOT NULL AND %s<>'' "
        "ORDER BY %s DESC LIMIT 3" % (pole, t, pole, pole, pole))]
    print('\n%s.%s: строк %d, непустых %d' % (t, pole, vsego, nepusto))
    print('   свежие значения: %s' % obrazcy)
    print('   с буквой T: %s' % all('T' in str(o) for o in obrazcy))

print('\nутилита времени панели:')
sys.path.insert(0, r'C:\centro2')
os.chdir(r'C:\centro2')
try:
    from dotenv import load_dotenv
    load_dotenv(r'C:\centro2\.env', override=True)
except Exception:  # noqa: BLE001
    pass
import importlib  # noqa: E402
for kand in ('app.services.centro_sales', 'app.centro_sales', 'app.core.centro_sales',
             'app.db.centro_sales'):
    try:
        m = importlib.import_module(kand)
        print('   %s.utcnow() = %r' % (kand, m.utcnow()))
        break
    except Exception as e:  # noqa: BLE001
        print('   %s — нет (%s)' % (kand, str(e)[:60]))
print('   datetime.utcnow() = %r'
      % datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'))

# Контроль на оба формата: если числа разойдутся, значит сравнение формата чувствительно
# и ноль в плитке был артефактом, а не фактом.
if 'activity_log' in tabl:
    print('')
    for metka, obrazec in (('с T', '%Y-%m-%dT%H:%M:%S'),
                           ('с пробелом', '%Y-%m-%d %H:%M:%S')):
        for dney in (1, 7, 30, 3650):
            porog = (datetime.datetime.utcnow()
                     - datetime.timedelta(days=dney)).strftime(obrazec)
            n = c.execute('SELECT COUNT(*) FROM activity_log WHERE created_at >= ?',
                          (porog,)).fetchone()[0]
            print('   activity_log, порог %-11s дней %-5d -> %d' % (metka, dney, n))
