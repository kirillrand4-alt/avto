# -*- coding: utf-8 -*-
import json, re
t = open(r'C:\sender\sender.yaml', encoding='utf-8', errors='replace').read()
i = t.find('signature')
print(json.dumps({'кусок': t[max(0,i-200):i+700]}, ensure_ascii=False, indent=1)[:1200])
