# -*- coding: utf-8 -*-
r"""fixKS (21.10): снимки баз КЦ (продажи и каталог) на дроп для проверки статистики в песочнице.
Только чтение живых баз (sqlite backup API); `--udalit` убирает снимки с дропа.

    python3 zapusk_na_servere.py fixKS_kopii_vniz.py
    python3 zapusk_na_servere.py fixKS_kopii_vniz.py --udalit
"""
import gzip
import os
import shutil
import sqlite3
import sys

DROP = r'C:\seostat\drop\drop-storage'
BAZY = {'fixKS-sales.db': r'C:\seostat\data\centro_sales.db', 'fixKS-kat.db': r'C:\seostat\data\centrifugal.db'}
for imya, put in BAZY.items():
    cel = os.path.join(DROP, imya)
    for f in (cel, cel + '.gz'):
        if os.path.exists(f):
            os.remove(f)
    if '--udalit' in sys.argv:
        print('убрано', imya)
        continue
    src = sqlite3.connect('file:%s?mode=ro' % put, uri=True)
    dst = sqlite3.connect(cel)
    src.backup(dst)
    dst.close()
    src.close()
    with open(cel, 'rb') as a, gzip.open(cel + '.gz', 'wb', 6) as b:
        shutil.copyfileobj(a, b)
    os.remove(cel)
    print(imya + '.gz', round(os.path.getsize(cel + '.gz') / 2**20, 1), 'МБ')
