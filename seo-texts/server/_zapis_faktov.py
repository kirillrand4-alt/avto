# -*- coding: utf-8 -*-
import json, re
t = open(r'C:\sender\server\site_facts.py', encoding='utf-8', errors='replace').read()
d = {'busy_timeout': t.count('busy_timeout'), 'connect_вызовов': t.count('sqlite3.connect')}
m = re.findall(r'.{120}sqlite3\.connect.{160}', t, re.S)
d['места'] = m[:3]
i = t.find('def sobrat')
d['sobrat'] = t[i:i+1200]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3000])
