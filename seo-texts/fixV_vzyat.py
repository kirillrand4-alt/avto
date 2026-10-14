# -*- coding: utf-8 -*-
"""fixV: только чтение. Кладёт на дроп архив кода панели (fixV-kod.zip) и печатает
пользователей панели (логин, роль, ФИО, город, активен, число назначений) и схему users.
Пароли/хеши не печатаются."""
import io
import os
import sqlite3
import time
import zipfile

APP = r'C:\centro2\app'
D = r'C:\seostat\drop\drop-storage'
OUT = os.path.join(D, 'fixV-kod.zip')
n = 0
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    for d, dirs, fs in os.walk(APP):
        if 'dokaz' in d.split(os.sep) or '__pycache__' in d:
            continue
        for f in fs:
            if f.endswith(('.py', '.html', '.css', '.js')):
                p = os.path.join(d, f)
                if os.path.getsize(p) > 3_000_000:
                    continue
                z.write(p, os.path.relpath(p, APP))
                n += 1
    for f in ('zapusk.py',):
        p = os.path.join(r'C:\centro2', f)
        if os.path.exists(p):
            z.write(p, '_koren/' + f)
print('кода файлов: %d (%d байт)' % (n, os.path.getsize(OUT)))
B = r'C:\centro2\data\centro_sales_meyer1.db'
c = sqlite3.connect('file:%s?mode=ro' % B, uri=True)
print('users schema:', c.execute("select sql from sqlite_master where name='users'").fetchone()[0])
kol = [x[1] for x in c.execute('pragma table_info(users)')]
print('users cols:', kol)
for r in c.execute("select id, username, role, coalesce(fio,''), coalesce(gorod,''), is_active from users order by id"):
    na = c.execute('select count(*) from company_assignment where username=?', (r[1],)).fetchone()[0]
    print('  ', r, 'назначений', na)
print('tables:', [x[0] for x in c.execute("select name from sqlite_master where type='table' order by name")])
print('замок:', os.path.exists(r'C:\centro2\_zamok.txt'), time.strftime('%H:%M:%S'))
if os.path.exists(r'C:\centro2\_zamok.txt'):
    print('   ', io.open(r'C:\centro2\_zamok.txt', encoding='utf-8').read())
