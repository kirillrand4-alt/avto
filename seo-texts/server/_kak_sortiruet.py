# -*- coding: utf-8 -*-
r"""Где реально сортируется очередь: смотрим сам обработчик /confirm/queue."""
import json
import re

п = r'C:\sender\sender\api\app.py'
with open(п, encoding='utf-8', errors='replace') as f:
    строки = f.read().splitlines()
нач = next((i for i, s in enumerate(строки) if '/confirm/queue' in s), 0)
куски = []
for i in range(нач, min(len(строки), нач + 220)):
    s = строки[i]
    if re.search(r'order|sort|score|ball|балл|ocenka|оценк|priorit', s, re.I):
        куски.append('%d: %s' % (i + 1, s.strip()[:140]))
print(json.dumps({'из_обработчика': куски[:25]}, ensure_ascii=False, indent=1)[:2600])
