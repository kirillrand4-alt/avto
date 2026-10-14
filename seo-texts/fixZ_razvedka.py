# -*- coding: utf-8 -*-
r"""fixZ: «Активность по часам» на статистике – кто попадает в таблицу и сколько отметок у каждого менеджера за сегодня.
Только чтение.

    python3 zapusk_na_servere.py fixZ_razvedka.py
"""
import io
import os
import re
import sqlite3

APP = r'C:\centro2\app'
for f in (r'templates\centro_stats.html', r'templates\_statblok.html', r'api\routes_centro_sales.py', r'services\centro_sales.py'):
    p = os.path.join(APP, f)
    if not os.path.exists(p):
        continue
    t = io.open(p, encoding='utf-8').read().splitlines()
    for i, s in enumerate(t, 1):
        if re.search(r'по часам|po_chasam|chasy|_chas\b|aktivn', s, re.I):
            print('%s:%d: %s' % (f, i, s.strip()[:230]))
s = sqlite3.connect('file:%s?mode=ro' % os.path.join(r'C:\centro2\data', 'centro_sales_meyer1.db'), uri=True)
print('\nпользователи:', s.execute("SELECT username, role, is_active, fio FROM users ORDER BY username").fetchall())
for t, kol in (('activity_log', 'created_at'), ('zvonok_sobytie', 'created_at'), ('company_state', 'updated_at')):
    try:
        print('%s сегодня (UTC с 2026-10-13T21:00):' % t,
              s.execute("SELECT username, COUNT(*) FROM %s WHERE %s >= '2026-10-13T21:00' GROUP BY 1" % (t, kol)).fetchall())
    except sqlite3.OperationalError as e:
        print(t, e)
