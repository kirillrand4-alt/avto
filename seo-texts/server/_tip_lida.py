# -*- coding: utf-8 -*-
"""Добавить поле otvet в тип Lead (типы живут в старом дереве, но нужны сборке)."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
из = []
for п in (r'C:\sender\sender\web\src\api\types.ts',):
    if not os.path.exists(п):
        из.append({'файл': п, 'беда': 'нет'})
        continue
    t = io.open(п, encoding='utf-8', errors='replace').read()
    m = re.search(r'export (?:interface|type) Lead\b.*?\n\}', t, re.S)
    из.append({'файл': п, 'Lead': (m.group(0)[:700] if m else 'не найден')})
print(json.dumps(из, ensure_ascii=False, indent=1)[:1600])
