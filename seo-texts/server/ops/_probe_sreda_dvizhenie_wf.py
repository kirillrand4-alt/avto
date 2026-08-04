# -*- coding: utf-8 -*-
"""Только чтение: кто и когда сдвинул поле medium в fact между моими прогонами."""
import json, os, sqlite3, time
from collections import Counter
БАЗА = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
cx = sqlite3.connect(f'file:{БАЗА}?mode=ro', uri=True, timeout=30)
расп = Counter()
пусто = 0
for (m,) in cx.execute("SELECT COALESCE(medium,'') FROM fact"):
    m = str(m).strip()
    расп[m[:40] or '<ПУСТО>'] += 1
    if not m:
        пусто += 1
файлы = {}
for п in (БАЗА, БАЗА + '-wal', r'C:\seostat\data\centro_sales.db'):
    try:
        s = os.stat(п)
        файлы[п] = {'байт': s.st_size,
                    'изменён': time.strftime('%Y-%m-%d %H:%M:%S',
                                             time.localtime(s.st_mtime))}
    except Exception as e:
        файлы[п] = str(e)
print(json.dumps({
    'сейчас': time.strftime('%Y-%m-%d %H:%M:%S'),
    'фактов': sum(расп.values()),
    'medium_пусто': пусто,
    'топ_значений_medium': расп.most_common(15),
    'файлы': файлы,
}, ensure_ascii=False, indent=1))
