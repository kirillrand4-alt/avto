# -*- coding: utf-8 -*-
import json, re
t = open(r'C:\sender\sender\probe_sync.py', encoding='utf-8', errors='replace').read()
d = {}
for имя in ('def _очередь', 'def __init__', 'def tick'):
    i = t.find(имя)
    d[имя] = t[i:i+1400] if i > 0 else 'нет'
d['batch_упоминания'] = re.findall(r'batch[^\n]{0,90}', t)[:6]
d['интервал'] = re.findall(r'(interval|интервал|period|секунд)[^\n]{0,80}', t)[:6]
print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])
