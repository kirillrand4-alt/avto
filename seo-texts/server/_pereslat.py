# -*- coding: utf-8 -*-
import json
t = open(r'C:\sender\sender\avtootvet.py', encoding='utf-8', errors='replace').read()
i = t.find('def переслать_на_новый_адрес')
print(json.dumps({'кусок': t[i:i+2400]}, ensure_ascii=False, indent=1)[:3400])
