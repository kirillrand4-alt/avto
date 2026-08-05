# -*- coding: utf-8 -*-
"""Показать строки файла по образцу, с окном вокруг. Читает, не трогает.

Запуск: python3 p25_grep_na_servere.py <файл> <образец> [окно]
"""
import io
import json
import os
import re
import sys

put = sys.argv[1] if len(sys.argv) > 1 else ''
obrazec = sys.argv[2] if len(sys.argv) > 2 else 'person'
okno = int(sys.argv[3]) if len(sys.argv) > 3 else 2

if not os.path.exists(put):
    print('файла нет: %s' % put)
    raise SystemExit
t = io.open(put, encoding='utf-8', errors='replace').read()
ls = t.split('\n')
rg = re.compile(obrazec, re.I)
nashli = 0
pokazany = set()
for i, s in enumerate(ls):
    if not rg.search(s):
        continue
    nashli += 1
    for j in range(max(0, i - okno), min(len(ls), i + okno + 1)):
        if j in pokazany:
            continue
        pokazany.add(j)
        print('%5d|%s %s' % (j + 1, '>' if j == i else ' ', ls[j][:160]))
    print('     |')
print('ИТОГ ' + json.dumps({'файл': put, 'образец': obrazec, 'строк всего': len(ls),
                            'совпадений': nashli}, ensure_ascii=False))
