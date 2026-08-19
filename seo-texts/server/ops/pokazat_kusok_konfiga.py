# -*- coding: utf-8 -*-
"""Показать кусок sender.yaml вокруг пулов — как он реально написан."""
import io
import sys

ФАЙЛ = r"C:\sender\sender.yaml"
что = sys.argv[1] if len(sys.argv) > 1 else "pool_yandex"
строки = io.open(ФАЙЛ, encoding="utf-8").read().split("\n")
for i, s in enumerate(строки):
    if что in s:
        нач = max(0, i - 6)
        кон = min(len(строки), i + 30)
        print(f"--- строки {нач+1}..{кон} ---")
        for k in range(нач, кон):
            print(f"{k+1:>4}| {строки[k]}")
        break
else:
    print(f"«{что}» в файле не найдено")
