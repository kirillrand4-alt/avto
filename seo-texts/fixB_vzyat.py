# -*- coding: utf-8 -*-
"""fixB: положить на дроп архив текущего кода копии панели (только чтение, без правок).

Берёт .py из app (без static/dokaz), шаблоны и css — в один zip `fixB-kod.zip` на дропе.
Плюс схема базы продаж (только CREATE-строки) и счётчики таблиц — для понимания, без данных.
"""
import io
import os
import sqlite3
import zipfile

APP = r'C:\centro2\app'
D = r'C:\seostat\drop\drop-storage'
OUT = os.path.join(D, 'fixB-kod.zip')
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
    # схема баз (без данных)
    sh = []
    for imya in ('centro_sales_meyer1.db', 'meyer_baza1.db'):
        p = os.path.join(r'C:\centro2\data', imya)
        try:
            c = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
            sh.append('==== ' + imya)
            for (s, nm) in c.execute("select sql, name from sqlite_master where sql is not null"):
                try:
                    k = c.execute('select count(*) from "%s"' % nm).fetchone()[0] if s.upper().startswith('CREATE TABLE') else ''
                except Exception:  # noqa: BLE001
                    k = '?'
                sh.append('%s;  -- %s' % (s, k))
            c.close()
        except Exception as e:  # noqa: BLE001
            sh.append('%s: %s' % (imya, e))
    z.writestr('_skhema.sql', '\n'.join(sh))
print('файлов: %d, архив: %s (%d байт)' % (n, OUT, os.path.getsize(OUT)))
# что лежит в .env по именам (без значений)
try:
    for l in io.open(r'C:\centro2\.env', encoding='utf-8', errors='replace'):
        if '=' in l and not l.strip().startswith('#'):
            k = l.split('=', 1)[0].strip()
            if 'DB' in k or 'ROOT' in k:
                print('env:', k, '=', l.split('=', 1)[1].strip())
except Exception as e:  # noqa: BLE001
    print('env:', e)
print('замок:', os.path.exists(r'C:\centro2\_zamok.txt'))
