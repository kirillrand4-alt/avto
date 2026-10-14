# -*- coding: utf-8 -*-
r"""fixU: где карточка панели Meyer выводит описание и паспорт компании (шаблоны, web.py). Только чтение.

    python3 zapusk_na_servere.py fixU_razvedka.py [строка_от строка_до]
"""
import io
import os
import re
import sys

APP = r'C:\centro2\app'
for kor, _, fajly in os.walk(APP):
    for f in fajly:
        if f.endswith(('.html', '.py')):
            p = os.path.join(kor, f)
            t = io.open(p, encoding='utf-8', errors='replace').read()
            n = len(re.findall(r'pasport-k|pasport_zag|Паспорт компании', t))
            if n:
                print('%s: %d' % (p, n))
t = io.open(os.path.join(APP, 'templates', 'centro.html'), encoding='utf-8').read().splitlines()
a, b = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (170, 182)
for i in range(a, b + 1):
    print('%d: %s' % (i, t[i - 1][:1500]))
