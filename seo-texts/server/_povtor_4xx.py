# -*- coding: utf-8 -*-
"""Что делает отправщик с временным отказом 4xx (серый список): повторяет ли."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
места = []
for d, _, fs in os.walk(r'C:\sender\sender'):
    if '__pycache__' in d or os.sep + 'tests' in d:
        continue
    for f in fs:
        if not f.endswith('.py'):
            continue
        p = os.path.join(d, f)
        try:
            t = io.open(p, encoding='utf-8', errors='replace').read()
        except Exception:  # noqa: BLE001
            continue
        строки = []
        for i, l in enumerate(t.splitlines()):
            if re.search(r'4[05]\d\b|temp_fail|tempfail|deferred|retry|повтор|'
                         r'greylist|сер(ый|ого) список|SMTPRecipientsRefused|'
                         r'SMTPResponseException|attempts?', l) \
                    and not l.strip().startswith('#'):
                строки.append((i + 1, l.strip()[:120]))
        if строки:
            места.append({'файл': f, 'мест': len(строки), 'строки': строки[:10]})
места.sort(key=lambda x: -x['мест'])
итог['где_про_повторы'] = места[:5]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:4800])
