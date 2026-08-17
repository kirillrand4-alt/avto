# -*- coding: utf-8 -*-
"""Как кампании 10/11 (Партия 935 КЦ/Meyer) выбирают получателей из группы:
по source? по division? где division берётся? Ищем в коде панели."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = []
for корень in (r'C:\sender\sender',):
    for d, _, fs in os.walk(корень):
        if '__pycache__' in d or os.sep + 'tests' in d:
            continue
        for f in fs:
            if not f.endswith('.py'):
                continue
            p = os.path.join(d, f)
            t = io.open(p, encoding='utf-8', errors='replace').read()
            строки = []
            for i, l in enumerate(t.splitlines()):
                if re.search(r'division|segment_division|campaign.*recipient|'
                             r"source\s*=|по группе|group_by_source", l, re.I) \
                        and not l.strip().startswith('#'):
                    строки.append((i + 1, l.strip()[:120]))
            if строки:
                итог.append({'файл': os.path.basename(p), 'мест': len(строки),
                             'строки': строки[:12]})
итог.sort(key=lambda x: -x['мест'])
print(json.dumps(итог[:6], ensure_ascii=False, indent=1)[:5500])
