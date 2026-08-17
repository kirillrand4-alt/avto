# -*- coding: utf-8 -*-
"""Каким путём панель принимает партии получателей: ищем в её коде."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
найдено = []
for корень in (r'C:\sender\sender',):
    for d, _, fs in os.walk(корень):
        if '__pycache__' in d or os.sep + 'tests' in d:
            continue
        for f in fs:
            if not f.endswith('.py'):
                continue
            p = os.path.join(d, f)
            t = io.open(p, encoding='utf-8', errors='replace').read()
            if not re.search(r'recipients', t):
                continue
            строки = []
            for i, l in enumerate(t.splitlines()):
                if re.search(r'def .*(import|upsert|add).*recipient|recipients\s*\(|'
                             r'INSERT\s+INTO\s+recipients|def import_', l, re.I):
                    строки.append((i + 1, l.strip()[:110]))
            if строки:
                найдено.append({'файл': os.path.basename(p), 'полный': p,
                                'места': строки[:8]})
print(json.dumps(найдено, ensure_ascii=False, indent=1)[:3000])
