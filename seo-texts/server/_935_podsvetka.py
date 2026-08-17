# -*- coding: utf-8 -*-
"""Чем панель подсвечивает фразы в теле письма на экране подтверждения."""
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
            места = []
            for i, l in enumerate(t.splitlines()):
                if re.search(r'подсвет|highlight|mark|<a |ssylk|фраза.*источ|'
                             r'источник.*фраз|fact.*link|proof', l, re.I):
                    места.append((i + 1, l.strip()[:120]))
            if места:
                итог.append({'файл': f, 'мест': len(места), 'строки': места[:10]})
итог.sort(key=lambda x: -x['мест'])
print(json.dumps(итог[:5], ensure_ascii=False, indent=1)[:5200])
