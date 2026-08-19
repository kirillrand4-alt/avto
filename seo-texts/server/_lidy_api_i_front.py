# -*- coding: utf-8 -*-
"""Ручки статусов лида и где во фронте живёт лента (исходники или только сборка)."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
t = io.open(r'C:\sender\sender\api\app.py', encoding='utf-8', errors='replace').read()
итог['ручки'] = [l.strip()[:120] for l in t.splitlines()
                 if re.search(r'@app\.(get|post|put|patch|delete)\("/leads', l)]
m = re.search(r'def lead_status.*?(?=\n@app\.|\ndef )', t, re.S)
итог['lead_status'] = m.group(0)[:1200] if m else ''
m2 = re.search(r'class LeadStatusBody.*?(?=\nclass |\n@app\.)', t, re.S)
итог['модель_тела'] = m2.group(0)[:400] if m2 else ''
# статусы в бизнес-логике
for имя in ('leads.py', 'lead_flow.py'):
    п = r'C:\sender\sender\%s' % имя
    if os.path.exists(п):
        tt = io.open(п, encoding='utf-8', errors='replace').read()
        m3 = re.search(r'(СТАТУСЫ|STATUSES|_STATUS\w*)\s*=\s*[\(\{\[].*?[\)\}\]]', tt, re.S)
        итог['статусы_в_%s' % имя] = m3.group(0)[:500] if m3 else ''
        итог['переходы_%s' % имя] = [l.strip()[:100] for l in tt.splitlines()
                                     if re.search(r'status|статус', l) and 'def ' in l][:10]
# фронт: есть ли исходники
исходники = []
for к in (r'C:\sender\web\src', r'C:\sender\web'):
    if os.path.exists(к):
        for d, _, fs in os.walk(к):
            if 'node_modules' in d or 'dist' in d:
                continue
            for f in fs:
                if f.endswith(('.tsx', '.ts', '.jsx', '.js', '.vue', '.html')):
                    исходники.append(os.path.relpath(os.path.join(d, f), к))
итог['исходники_фронта'] = исходники[:25]
итог['исходников_всего'] = len(исходники)
print(json.dumps(итог, ensure_ascii=False, indent=1)[:4200])
