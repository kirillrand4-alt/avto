# -*- coding: utf-8 -*-
"""Текст файла по полному пути (первые N строк): fayl_tekst.py <путь> [N=80]. Только чтение."""
import io
import sys
N = int(sys.argv[2]) if len(sys.argv) > 2 else 80
for i, s in enumerate(io.open(sys.argv[1], encoding="utf-8", errors="replace"), 1):
    if i > N:
        break
    print("%4d: %s" % (i, s.rstrip()))
