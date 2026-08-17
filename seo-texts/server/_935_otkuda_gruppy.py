# -*- coding: utf-8 -*-
"""Откуда выпадашка «группа» на экране подтверждения берёт значения и счётчики."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = []
for корень in (r'C:\sender\sender',):
    for d, _, fs in os.walk(корень):
        if '__pycache__' in d:
            continue
        for f in fs:
            if not (f.endswith('.py') or f.endswith('.html') or f.endswith('.js')):
                continue
            p = os.path.join(d, f)
            try:
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if not re.search(r'писем в группе|все группы|group', t, re.I):
                continue
            места = []
            for i, l in enumerate(t.splitlines()):
                if re.search(r'писем в группе|все группы|group_options|'
                             r'groups?\s*=|by_group|group_counts|группа', l, re.I):
                    места.append((i + 1, l.strip()[:130]))
            if места:
                итог.append({'файл': f, 'мест': len(места), 'строки': места[:14]})
итог.sort(key=lambda x: -x['мест'])
print(json.dumps(итог[:4], ensure_ascii=False, indent=1)[:5400])
