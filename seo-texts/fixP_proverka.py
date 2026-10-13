# -*- coding: utf-8 -*-
r"""fixP: независимая проверка после fixQ – по 270/120, убранных 330 нет в рабочей панели, вердикт у всех. Только чтение.

    python3 zapusk_na_servere.py fixP_proverka.py
"""
import collections
import io
import json
import os
import sqlite3
import urllib.request

KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'


def ro(put):
    return sqlite3.connect('file:%s?mode=ro' % put, uri=True, timeout=30)


kat, s = ro(KAT), ro(SALES)
nazn = dict(s.execute('SELECT inn, username FROM company_assignment'))
print('назначений по менеджерам:', dict(sorted(collections.Counter(nazn.values()).items())))
v_kat = {r[0] for r in kat.execute('SELECT inn FROM company')}
print('в каталоге %d, назначено %d, назначено без каталога %d, в каталоге без назначения %d'
      % (len(v_kat), len(nazn), len(set(nazn) - v_kat), len(v_kat - set(nazn))))
ubr = [x['inn'] for x in json.load(io.open(os.path.join(DROP, 'fixP-ubrat.json'), encoding='utf-8'))]
print('из 330 убранных: в каталоге %d, в назначениях %d, в архиве каталога %d' % (
    len(set(ubr) & v_kat), len(set(ubr) & set(nazn)),
    kat.execute('SELECT COUNT(DISTINCT inn) FROM arhiv_company WHERE inn IN (%s)' % ','.join('?' * len(ubr)), ubr).fetchone()[0]))
print('вердикт:', dict(kat.execute('SELECT COALESCE(meyer_verdikt, "—"), COUNT(*) FROM company GROUP BY 1')))
st = collections.defaultdict(collections.Counter)
for inn, u, stup in s.execute('SELECT inn, username, stupen_ocheredi FROM company_assignment'):
    st[u][stup] += 1
print('ступени по менеджерам:')
for u in sorted(st):
    print('  %s %s' % (u, dict(sorted(st[u].items(), reverse=True))))
try:
    print('панель /login:', urllib.request.urlopen('http://127.0.0.1:8016/obzvon-meyer/centro/login', timeout=15).status)
except Exception as e:  # noqa: BLE001
    print('панель /login:', repr(e))
