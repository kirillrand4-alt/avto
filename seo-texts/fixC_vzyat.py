# -*- coding: utf-8 -*-
"""fixC: только чтение. Кладёт на дроп архив кода панели и копию каталога meyer_baza1.db
(через sqlite backup API, без записи в боевую базу) — для разбора контактов/людей."""
import os
import sqlite3
import time
import zipfile

APP = r'C:\centro2\app'
D = r'C:\seostat\drop\drop-storage'
OUT = os.path.join(D, 'fixC-kod.zip')
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
print('кода файлов: %d (%d байт)' % (n, os.path.getsize(OUT)))
src = sqlite3.connect('file:%s?mode=ro' % r'C:\centro2\data\meyer_baza1.db', uri=True)
tmp = os.path.join(D, 'fixC-katalog.db')
if os.path.exists(tmp):
    os.remove(tmp)
dst = sqlite3.connect(tmp)
src.backup(dst)
dst.close()
src.close()
zp = os.path.join(D, 'fixC-katalog.zip')
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(tmp, 'meyer_baza1.db')
os.remove(tmp)
print('каталог: %s %d байт' % (zp, os.path.getsize(zp)))
print('размер боевой базы:', os.path.getsize(r'C:\centro2\data\meyer_baza1.db'))
print('замок:', os.path.exists(r'C:\centro2\_zamok.txt'), time.strftime('%H:%M:%S'))
