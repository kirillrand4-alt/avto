# -*- coding: utf-8 -*-
import json, re
t = open(r'C:\sender\sender\leaddesk.py', encoding='utf-8', errors='replace').read()
m = re.search(r'_TRANSITIONS\s*[:=].*?\}\s*\n', t, re.S)
d = {'_TRANSITIONS': m.group(0)[:1400] if m else 'нет'}
m2 = re.search(r'_STATUSES?\s*[:=][^\n]{0,300}', t)
d['статусы'] = m2.group(0) if m2 else ''
print(json.dumps(d, ensure_ascii=False, indent=1)[:2400])
