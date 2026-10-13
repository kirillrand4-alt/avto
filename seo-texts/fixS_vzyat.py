# -*- coding: utf-8 -*-
"""fixS: только чтение. Кладёт на дроп архив кода панели (fixS-kod.zip). Печатает состояние замка."""
import io
import os
import sys
import time
import zipfile

APP = r'C:\centro2\app'
D = r'C:\seostat\drop\drop-storage'
PRE = 'fixS-' + (sys.argv[1] if len(sys.argv) > 1 else '')
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
print('замок:', os.path.exists(r'C:\centro2\_zamok.txt'), time.strftime('%H:%M:%S'))
if os.path.exists(r'C:\centro2\_zamok.txt'):
    print('   ', io.open(r'C:\centro2\_zamok.txt', encoding='utf-8').read())
