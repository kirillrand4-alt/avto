# -*- coding: utf-8 -*-
r"""fixZ: поиск по коду панели (только чтение).  python3 zapusk_na_servere.py fixZ_grep.py <регэксп> [файл]"""
import io
import re
import sys

fajly = [sys.argv[2]] if len(sys.argv) > 2 else [r'C:\centro2\app\api\routes_centro_sales.py', r'C:\centro2\app\services\centro_sales.py']
for f in fajly:
    for i, s in enumerate(io.open(f, encoding='utf-8').read().splitlines(), 1):
        if re.search(sys.argv[1], s):
            print('%s:%d: %s' % (f.split('\\')[-1], i, s.strip()[:200]))
