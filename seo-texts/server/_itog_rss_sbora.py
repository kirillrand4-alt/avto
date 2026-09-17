# -*- coding: utf-8 -*-
"""Итог прогона по донорским лентам — он закончился в 09:03."""
import json, os, re

DIR = r'C:\sender\server'
o = {}
for имя in ('rss_sbor_1709-0557.log', 'rss_cepochka_1709-0557.log'):
    п = os.path.join(DIR, имя)
    if not os.path.exists(п):
        continue
    with open(п, encoding='utf-8', errors='replace') as f:
        т = f.read()
    m = re.search(r'"summary"\s*:\s*\{.*', т, re.S)
    o[имя] = (m.group(0)[:900] if m else т[-700:])
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
