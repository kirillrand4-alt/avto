# -*- coding: utf-8 -*-
r"""fixKR (21.10): проверка после раздела компаний user3 панели КЦ – только чтение.

Сколько компаний назначено каждому, сколько из них не скрыто, сколько осталось у user3, сколько строк помечено
vladelec_do_fixKR и что комментарии/журнал по этим компаниям на месте.

    python3 zapusk_na_servere.py fixKR_proverka.py
"""
import sqlite3

SALES = r'C:\seostat\data\centro_sales.db'

s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True, timeout=30)
skryto = {r[0] for r in s.execute("SELECT DISTINCT inn FROM hidden_item WHERE kind='company'")}
for u, in s.execute('SELECT DISTINCT username FROM company_assignment ORDER BY 1'):
    inn = [r[0] for r in s.execute('SELECT inn FROM company_assignment WHERE username=?', (u,))]
    print('%-6s назначено %4d, не скрыто %4d' % (u, len(inn), sum(1 for i in inn if i not in skryto)))
pomech = s.execute('SELECT vladelec_do_fixKR, username, COUNT(*) FROM company_assignment '
                   'WHERE vladelec_do_fixKR IS NOT NULL GROUP BY 1, 2').fetchall()
print('перенесено fixKR:', pomech)
inn3 = [r[0] for r in s.execute('SELECT inn FROM company_assignment WHERE vladelec_do_fixKR IS NOT NULL')]
dubli = s.execute('SELECT COUNT(*) FROM (SELECT inn FROM company_assignment GROUP BY inn HAVING COUNT(*) > 1)').fetchone()[0]
print('ИНН с двумя владельцами:', dubli)
q = ','.join('?' * len(inn3))
for t in ('company_comment', 'activity_log'):
    try:
        print('%s по перенесённым: %d' % (t, s.execute('SELECT COUNT(*) FROM %s WHERE inn IN (%s)' % (t, q), inn3).fetchone()[0]))
    except sqlite3.OperationalError as e:
        print(t, e)
