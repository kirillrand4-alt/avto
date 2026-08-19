# -*- coding: utf-8 -*-
"""Какие статусы принимает лид и где живёт их список."""
import io, json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
итог = {}
for d, _, fs in os.walk(r'C:\sender\sender'):
    if '__pycache__' in d:
        continue
    for f in fs:
        if not f.endswith('.py'):
            continue
        t = io.open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
        if 'def set_status' in t and 'lead' in t.lower():
            итог['файл'] = os.path.join(d, f)
            m = re.search(r'(СТАТУСЫ|STATUSES|ALLOWED_STATUS\w*|_STATUS\w*)\s*[:=]\s*'
                          r'[\(\{\[][^)}\]]*[\)\}\]]', t)
            итог['список_статусов'] = m.group(0)[:400] if m else ''
            m2 = re.search(r'def set_status.*?(?=\n    def )', t, re.S)
            итог['set_status'] = m2.group(0)[:900] if m2 else ''
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2600])
