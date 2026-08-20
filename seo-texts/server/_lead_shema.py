# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
d = {'leads': [r[1] for r in c.execute('pragma table_info(leads)')]}
c.close()
t = open(r'C:\sender\sender\leaddesk.py', encoding='utf-8', errors='replace').read()
i = t.find('def push_warm_lead')
d['push_warm_lead'] = t[i:i+1400] if i > 0 else 'нет'
print(json.dumps(d, ensure_ascii=False, indent=1)[:2600])
