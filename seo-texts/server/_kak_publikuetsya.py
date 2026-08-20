# -*- coding: utf-8 -*-
import json, os, re
п = r'C:\sender\sender\addr_probe.py'
t = open(п, encoding='utf-8', errors='replace').read()
d = {'функции': re.findall(r'\n    def (\w+)', t)}
i = t.find('def опубликовать')
if i < 0:
    i = t.find('def publish')
d['кусок_публикации'] = t[i:i+2000] if i > 0 else 'не найдено'
print(json.dumps(d, ensure_ascii=False, indent=1)[:3000])
