# -*- coding: utf-8 -*-
r"""Ищем сортировку очереди по всему коду панели."""
import json
import os
import re

найдено = {}
for корень in (r'C:\sender\sender', r'C:\sender\sender\api'):
    for имя in sorted(os.listdir(корень)):
        if not имя.endswith('.py'):
            continue
        п = os.path.join(корень, имя)
        try:
            строки = open(п, encoding='utf-8', errors='replace').read().splitlines()
        except OSError:
            continue
        стр = []
        for i, s in enumerate(строки):
            if re.search(r'order\s*==\s*[\'"]score|order_by|ORDER BY|key=lambda.*(ball|score|prior)', s, re.I):
                стр.append('%d: %s' % (i + 1, s.strip()[:130]))
        if стр:
            найдено[имя] = стр[:8]
print(json.dumps(найдено, ensure_ascii=False, indent=1)[:2800])
