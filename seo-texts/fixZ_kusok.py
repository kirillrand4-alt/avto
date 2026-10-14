# -*- coding: utf-8 -*-
r"""fixZ: показать кусок routes_centro_sales.py (строки от–до). Только чтение.

    python3 zapusk_na_servere.py fixZ_kusok.py 1860 1980
"""
import io
import sys

t = io.open(r'C:\centro2\app\api\routes_centro_sales.py', encoding='utf-8').read().splitlines()
a, b = int(sys.argv[1]), int(sys.argv[2])
for i in range(a, min(b, len(t)) + 1):
    print('%d: %s' % (i, t[i - 1][:200]))
