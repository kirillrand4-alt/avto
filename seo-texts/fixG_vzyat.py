# -*- coding: utf-8 -*-
"""fixG: только чтение. Кладёт на дроп архив кода панели (fixG-kod.zip) и копии каталога и
базы продаж (fixG-bazy.zip; sqlite backup из read-only соединения). Печатает состояние замка."""
import io
import os
import sqlite3
import sys
import time
import zipfile

APP = r'C:\centro2\app'
D = r'C:\seostat\drop\drop-storage'
PRE = 'fixG-' + (sys.argv[1] if len(sys.argv) > 1 else '')
OUT = os.path.join(D, PRE + 'kod.zip')
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
zp = os.path.join(D, PRE + 'bazy.zip')
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for imya in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
        src = sqlite3.connect('file:%s?mode=ro' % os.path.join(r'C:\centro2\data', imya), uri=True)
        tmp = os.path.join(D, 'fixG-tmp-' + imya)
        if os.path.exists(tmp):
            os.remove(tmp)
        dst = sqlite3.connect(tmp)
        src.backup(dst)
        dst.close()
        src.close()
        z.write(tmp, imya)
        os.remove(tmp)
print('базы: %s %d байт' % (zp, os.path.getsize(zp)))
print('замок:', os.path.exists(r'C:\centro2\_zamok.txt'), time.strftime('%H:%M:%S'))
if os.path.exists(r'C:\centro2\_zamok.txt'):
    print('   ', io.open(r'C:\centro2\_zamok.txt', encoding='utf-8').read())
