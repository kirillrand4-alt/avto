# -*- coding: utf-8 -*-
"""Где в коде панели считается «имя надёжно» и какие поля оно читает."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
найдено = []
for корень in (r'C:\sender\sender', r'C:\sender\enrich_panel'):
    for d, _, fs in os.walk(корень):
        if '__pycache__' in d or os.sep + 'tests' in d:
            continue
        for f in fs:
            if not f.endswith('.py'):
                continue
            p = os.path.join(d, f)
            try:
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            if 'надёж' not in t and 'nadyozh' not in t and 'contact_name' not in t:
                continue
            ls = t.splitlines()
            куски = []
            for i, l in enumerate(ls):
                if re.search(r'надёж|nadyozh|contact_name', l):
                    куски.append({'строка': i + 1,
                                  'текст': '\n'.join(x[:110] for x in ls[max(0, i - 2):i + 6])})
            if куски:
                найдено.append({'файл': p, 'мест': len(куски), 'первые': куски[:3]})
print(json.dumps(найдено, ensure_ascii=False, indent=1)[:3200])
