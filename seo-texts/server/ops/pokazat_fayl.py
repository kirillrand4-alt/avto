# -*- coding: utf-8 -*-
"""Показать файл сервера: pokazat_fayl.py <путь> [строк=80]"""
import io
import sys
n = int(sys.argv[2]) if len(sys.argv) > 2 else 80
for i, с in enumerate(io.open(sys.argv[1], encoding="utf-8", errors="replace")):
    if i >= n:
        break
    print(с.rstrip()[:200])
print("=== ФАЙЛ ===")
