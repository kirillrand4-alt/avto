# -*- coding: utf-8 -*-
r"""fixW: сегменты компаний панели – у кого пусто, какие сегменты MEYER-7 и отрасли; как строится выпадающий список.
Только чтение.

    python3 zapusk_na_servere.py fixW_razvedka.py
"""
import collections
import io
import os
import re
import sqlite3

KOREN = r'C:\centro2'
k = sqlite3.connect('file:%s?mode=ro' % os.path.join(KOREN, 'data', 'meyer_baza1.db'), uri=True)
rows = k.execute("SELECT COALESCE(segment,''), COALESCE(segment_meyer7,''), COALESCE(otrasl,'') FROM company").fetchall()
print('всего', len(rows), '; сегмент пуст', sum(1 for r in rows if not r[0].strip()))
print('\nсегменты панели:', sorted(collections.Counter(s for r in rows for s in r[0].split(' | ') if s.strip()).items()))
print('\nпустой сегмент -> сегмент MEYER-7:')
for v, n in collections.Counter(r[1] for r in rows if not r[0].strip()).most_common():
    print('  %4d  %s' % (n, v))
print('\nпустой сегмент -> отрасль:')
for v, n in collections.Counter(r[2] for r in rows if not r[0].strip()).most_common():
    print('  %4d  %s' % (n, v))
print('\nсегмент 3 -> сегмент MEYER-7 (топ):', collections.Counter(r[1] for r in rows if '3 пищевые' in r[0]).most_common(8))
for f in (r'app\api\routes_centro_sales.py', r'app\services\centro_catalog.py', r'app\services\centro_sales.py', r'app\web.py'):
    t = io.open(os.path.join(KOREN, f), encoding='utf-8').read().splitlines()
    for i, s in enumerate(t, 1):
        if re.search(r'segment', s) and re.search(r'choices|vybor|spisok|options|distinct|segmenty|Counter|split', s):
            print('%s:%d: %s' % (f, i, s.strip()[:200]))
