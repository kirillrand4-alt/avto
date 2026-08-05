# -*- coding: utf-8 -*-
"""Найти шаблон карточки и показать, чем он рисует человека.

`persons()` отдаёт строку целиком (`SELECT *`), значит мои колонки уже лежат в словаре
человека и доехали до шаблона. Дальше всё решает шаблон: что он печатает, то продавец и
видит. Прибор находит шаблоны, где встречается `persons`, и показывает кусок про
человека — чтобы правку делать по месту, а не наугад.

Ничего не пишет.
"""
import collections
import io
import json
import os
import re

KORNI = (r'C:\seostat\app', r'C:\seostat')
RASSH = ('.html', '.jinja', '.jinja2', '.j2', '.htm')

sch = collections.Counter()
nashli = []
seen = set()
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if re.search(r'[\\/](?:node_modules|\.git|__pycache__)[\\/]', put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith(RASSH):
                continue
            p = os.path.join(put, f)
            if p in seen:
                continue
            seen.add(p)
            try:
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            sch['шаблонов просмотрено'] += 1
            if 'persons' not in t:
                continue
            nashli.append(p)
            ls = t.split('\n')
            print('\n===== %s' % p)
            pokazany = set()
            for i, s in enumerate(ls):
                if not re.search(r'persons|\bp\.person\b|p\.role|p\.position|privyazka', s):
                    continue
                for j in range(max(0, i - 4), min(len(ls), i + 9)):
                    if j in pokazany:
                        continue
                    pokazany.add(j)
                    print('%5d| %s' % (j + 1, ls[j][:150]))
                print('     |')
            sch['шаблонов с людьми'] += 1

for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'шаблоны с людьми': [x[-60:] for x in nashli]},
                           ensure_ascii=False))
