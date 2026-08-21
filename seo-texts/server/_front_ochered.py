# -*- coding: utf-8 -*-
r"""Что фронт шлёт в /confirm/queue: передаёт ли он division и где фильтрует."""
import json
import os
import re

d = {}
# 1. Исходники экрана очереди.
for корень in (r'C:\sender\_tmp\web-pravki', r'C:\sender\_tmp\web-src-iz-mapy'):
    if not os.path.isdir(корень):
        continue
    for путь, _к, файлы in os.walk(корень):
        for ф in файлы:
            if not ф.endswith(('.tsx', '.ts')):
                continue
            п = os.path.join(путь, ф)
            with open(п, encoding='utf-8', errors='replace') as fh:
                строки = fh.read().splitlines()
            если = [i for i, s in enumerate(строки)
                    if 'confirm/queue' in s or 'confirmQueue' in s]
            if not если:
                continue
            узел = d.setdefault('исходники', {}).setdefault(
                п.replace(корень, '<' + os.path.basename(корень) + '>'), [])
            for i in если:
                узел.append('%d: %s' % (i + 1, строки[i].strip()[:130]))
            # рядом — как считается видимость и фильтр направления
            for i, s in enumerate(строки):
                if re.search(r'division|напр|kc\b|meyer', s, re.I) and len(узел) < 30:
                    узел.append('%d: %s' % (i + 1, s.strip()[:130]))

# 2. Что реально лежит в собранном бандле.
dist = r'C:\sender\web\dist'
if os.path.isdir(dist):
    d['сборка'] = {}
    for путь, _к, файлы in os.walk(dist):
        for ф in файлы:
            if not ф.endswith('.js'):
                continue
            п = os.path.join(путь, ф)
            with open(п, encoding='utf-8', errors='replace') as fh:
                т = fh.read()
            if 'confirm/queue' in т:
                i = т.find('confirm/queue')
                d['сборка'][ф] = {
                    'байт': len(т),
                    'изменён': os.path.getmtime(п),
                    'кусок': т[max(0, i - 260):i + 260],
                    'есть_division_в_запросе': 'division' in т[max(0, i - 400):i + 400],
                }
print(json.dumps(d, ensure_ascii=False, indent=1)[:5200])
