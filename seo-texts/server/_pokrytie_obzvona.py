# -*- coding: utf-8 -*-
"""Все ли сайты из базы обзвона попали в очередь/кэш."""
import json
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ZENNO = r'C:\seostat\drop\zenno'
KESH = r'C:\seostat\drop\pagecache'
отдано = {l.strip() for l in open(os.path.join(ZENNO, 'otdano.txt'),
                                  encoding='utf-8', errors='replace') if l.strip()}
обойдено = {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}
в_очереди = set()
for l in open(os.path.join(ZENNO, 'ochered.txt'), encoding='utf-8', errors='replace'):
    if l.strip():
        в_очереди.add(l.split(';')[0].strip())
sys.path.insert(0, r'C:\sender\server')
try:
    import ploshchadki as PL
    площадка = PL.из_списка
except Exception:  # noqa: BLE001
    площадка = lambda u: ''
o = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/obzvon-index.db', uri=True)
свод = {'строк_с_сайтом': 0, 'в_очереди': 0, 'обойдены': 0, 'отдавали_ранее': 0,
        'площадки': 0, 'НЕ_ОХВАЧЕНЫ': 0}
не_охвачены = []
for inn, сайты in o.execute("select inn, coalesce(sites,'') from obzvon "
                            "where coalesce(sites,'')<>''"):
    inn = ''.join(c for c in str(inn or '') if c.isdigit())
    if not inn:
        continue
    свод['строк_с_сайтом'] += 1
    if inn in обойдено:
        свод['обойдены'] += 1
        continue
    if inn in в_очереди:
        свод['в_очереди'] += 1
        continue
    if inn in отдано:
        свод['отдавали_ранее'] += 1
        continue
    u = re.split(r'[;,\s]+', str(сайты).strip())[0]
    if площадка(u):
        свод['площадки'] += 1
        continue
    свод['НЕ_ОХВАЧЕНЫ'] += 1
    if len(не_охвачены) < 5:
        не_охвачены.append('%s;%s' % (inn, u))
o.close()
свод['примеры_неохваченных'] = не_охвачены
print(json.dumps(свод, ensure_ascii=False, indent=1))
