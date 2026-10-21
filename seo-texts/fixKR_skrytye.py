# -*- coding: utf-8 -*-
r"""fixKR (21.10): скрытые компании панели КЦ (hidden_item) – кто скрыл, когда, с какой причиной; как скрытие влияет на
показ (по пользователю или для всех). Только чтение.

    python3 zapusk_na_servere.py fixKR_skrytye.py
"""
import io
import re
import sqlite3

s = sqlite3.connect(r'file:C:\seostat\data\centro_sales.db?mode=ro', uri=True)
kol = [r[1] for r in s.execute('PRAGMA table_info(hidden_item)')]
print('колонки hidden_item:', kol)
print('всего строк:', s.execute('SELECT COUNT(*) FROM hidden_item').fetchone()[0])
grp = [c for c in kol if c in ('kind', 'username', 'hidden_by', 'reason', 'prichina')]
if grp:
    print('по %s:' % grp, s.execute('SELECT %s, COUNT(*) FROM hidden_item GROUP BY %s ORDER BY 2 DESC LIMIT 20' % (', '.join(grp), ', '.join(grp))).fetchall())
dk = next((c for c in kol if 'created' in c or 'at' == c[-2:]), None)
if dk:
    print('даты у компаний user3:', s.execute("SELECT substr(%s,1,10), COUNT(*) FROM hidden_item WHERE inn IN (SELECT inn FROM company_assignment "
                                               "WHERE username='user3') GROUP BY 1" % dk).fetchall())
print('пример строк у user3:', s.execute("SELECT * FROM hidden_item WHERE inn IN (SELECT inn FROM company_assignment WHERE username='user3') LIMIT 3").fetchall())
t = io.open(r'C:\seostat\app\api\routes_centro_sales.py', encoding='utf-8').read().splitlines()
t += io.open(r'C:\seostat\app\services\centro_sales.py', encoding='utf-8').read().splitlines()
print('\nкод про hidden_item:')
for s_ in t:
    if 'hidden_item' in s_:
        print('   ' + s_.strip()[:170])
