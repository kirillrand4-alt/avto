# -*- coding: utf-8 -*-
import json
t = open(r'C:\sender\sender\addr_probe.py', encoding='utf-8', errors='replace').read()
i = t.find('def _save')
print(json.dumps({'кусок': t[i:i+1200]}, ensure_ascii=False, indent=1))
