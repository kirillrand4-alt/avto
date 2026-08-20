# -*- coding: utf-8 -*-
import json, re, os
п = r'C:\sender\sender\addr_probe.py'
t = open(п, encoding='utf-8', errors='replace').read() if os.path.exists(п) else ''
куски = []
for m in re.finditer(r'(INSERT|REPLACE|UPDATE)[^;\'"]{0,220}addr_probe[^;\'"]{0,320}', t, re.I):
    куски.append(m.group(0)[:340])
# и как пишется hard-bounce
hb = [m.group(0)[:300] for m in re.finditer(r'.{160}hard-bounce.{140}', t, re.S)]
print(json.dumps({'файл_есть': bool(t), 'sql': куски[:4], 'hard_bounce': hb[:2]},
                 ensure_ascii=False, indent=1))
