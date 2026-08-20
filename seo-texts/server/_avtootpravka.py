# -*- coding: utf-8 -*-
import json, re, os
d = {}
for п in (r'C:\sender\sender\confirm.py', r'C:\sender\sender\api\app.py',
          r'C:\sender\sender\scheduler.py', r'C:\sender\sender\sender.py'):
    if not os.path.exists(п): continue
    t = open(п, encoding='utf-8', errors='replace').read()
    куски = []
    for m in re.finditer(r'.{200}auto_send_enabled.{260}', t, re.S):
        куски.append(m.group(0))
    if куски:
        d[os.path.basename(п)] = куски[:2]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3200])
