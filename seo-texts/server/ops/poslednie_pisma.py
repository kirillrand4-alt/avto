# -*- coding: utf-8 -*-
"""Последние N годных писем из журнала: poslednie_pisma.py <журнал в _ops> [N]"""
import io
import json
import sys
пут = r"C:\sender\_ops" + "\\" + sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 2
ок = []
for с in io.open(пут, encoding="utf-8", errors="replace"):
    if '"итог"' in с and '"ок": true' in с:
        ок.append(с)
for с in ок[-N:]:
    з = json.loads(с)
    print("##", з.get("имя"), "|", з.get("день"))
    print("Тема:", з.get("тема"))
    print(з.get("тело"))
    print()
print("=== ПОСЛЕДНИЕ ПИСЬМА ===")
