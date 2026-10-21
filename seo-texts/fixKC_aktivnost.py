# -*- coding: utf-8 -*-
r"""fixKC (21.10): последние отметки менеджеров панели КЦ (activity_log, company_state, комментарии) за всё время. Только чтение.

    python3 zapusk_na_servere.py fixKC_aktivnost.py
"""
import sqlite3

s = sqlite3.connect(r'file:C:\seostat\data\centro_sales.db?mode=ro', uri=True)
for t, kol in (('activity_log', 'created_at'), ('company_state', 'updated_at'), ('company_comment', 'created_at')):
    try:
        print('%s: %s' % (t, s.execute('SELECT username, COUNT(*), MIN(%s), MAX(%s) FROM %s GROUP BY 1' % (kol, kol, t)).fetchall()))
    except sqlite3.OperationalError as e:
        print(t, e)
print('activity_log user2 по месяцам:', s.execute(
    "SELECT substr(created_at,1,7), COUNT(*) FROM activity_log WHERE username='user2' GROUP BY 1 ORDER BY 1").fetchall())
