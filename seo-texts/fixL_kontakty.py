# -*- coding: utf-8 -*-
"""fixL: только чтение. Контакты и люди компании (номера замаскированы) – проверить выбор «лучшего ЛПР» для окна лида.
    python3 zapusk_na_servere.py fixL_kontakty.py 7130001590"""
import re
import sqlite3
import sys

inn = sys.argv[1] if len(sys.argv) > 1 else '7130001590'
k = sqlite3.connect('file:%s?mode=ro' % r'C:\centro2\data\meyer_baza1.db', uri=True)
k.row_factory = sqlite3.Row


def m(v):
    return re.sub(r'\d(?=(?:\D*\d){2})', '•', str(v or ''))


for r in k.execute('SELECT id, kind, value, person, position, role, vid_nomera, nomer_ne_lichnyy, chuzhoy_istochnik FROM contact WHERE inn=? ORDER BY id', (inn,)):
    d = dict(r)
    d['value'] = m(d['value']) if d['kind'] == 'phone' else d['value']
    print('contact', d)
for r in k.execute('SELECT id, person, position, role, phone, sprosit_u_priemnoy FROM person WHERE inn=? ORDER BY id', (inn,)):
    d = dict(r)
    d['phone'] = m(d['phone'])
    print('person', d)
print('direktor:', tuple(k.execute('SELECT direktor, lpr_kratko FROM company WHERE inn=?', (inn,)).fetchone()))
print('примеры direktor:', [tuple(r) for r in k.execute("SELECT direktor FROM company WHERE COALESCE(direktor,'')<>'' LIMIT 8")])
