# -*- coding: utf-8 -*-
r"""fixIN (20.10): какие базы залиты в панель Meyer (метка «Базы» и её описание) и список ИНН всех компаний панели
(ИНН, название, регион, менеджер, базы) – CSV на дроп `meyer-panel-inn-20.10.csv`. Без телефонов. Только чтение.

    python3 zapusk_na_servere.py fixIN_vygruzka.py
"""
import collections
import csv
import io
import os
import sqlite3

D = r'C:\centro2\data'
k = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'meyer_baza1.db'), uri=True)
k.row_factory = sqlite3.Row
s = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'centro_sales_meyer1.db'), uri=True)
nazn = dict(s.execute('SELECT inn, username FROM company_assignment'))
fio = dict(s.execute("SELECT username, COALESCE(fio,'') FROM users"))
rows = [dict(r) for r in k.execute("SELECT inn, predpriyatie, region, COALESCE(bazy,'') AS bazy, COALESCE(bazy_opisanie,'') AS bo, "
                                   "COALESCE(meyer_verdikt,'') AS v FROM company ORDER BY inn")]
sch, opis = collections.Counter(), {}
for r in rows:
    for i, b in enumerate([x.strip() for x in r['bazy'].split(' | ') if x.strip()] or ['(без метки)']):
        sch[b] += 1
        o = [x.strip() for x in r['bo'].split(' | ')]
        if b not in opis and i < len(o) and o[i]:
            opis[b] = o[i]
print('компаний в панели: %d' % len(rows))
for b, n in sorted(sch.items()):
    print('%5d  %s  —  %s' % (n, b, opis.get(b, '')[:260]))
put = r'C:\seostat\drop\drop-storage\meyer-panel-inn-20.10.csv'
with io.open(put, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['ИНН / УНП', 'Компания', 'Регион', 'Менеджер', 'Логин', 'Базы', 'Покупатель Meyer'])
    for r in rows:
        u = nazn.get(r['inn'], '')
        w.writerow([r['inn'], r['predpriyatie'], r['region'] or '', fio.get(u, ''), u, r['bazy'], r['v']])
print('\nCSV: meyer-panel-inn-20.10.csv, строк %d' % len(rows))
