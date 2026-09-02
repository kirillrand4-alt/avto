# -*- coding: utf-8 -*-
"""Только чтение: подбор ящика для писем кампании 12 через боевую сборку
(wiring.py), с живым индексом обзвона."""
import inspect
import io
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
import sender.wiring as W  # noqa: E402

print("=== фабрики в wiring.py ===")
for имя in dir(W):
    о = getattr(W, имя)
    if callable(о) and not имя.startswith("_") and имя[0].islower():
        try:
            print("  %-24s %s" % (имя, str(inspect.signature(о))[:110]))
        except Exception:
            pass

т = io.open(r"C:\sender\sender\wiring.py", encoding="utf-8", errors="replace").read()
лн = т.splitlines()
print("\n=== wiring.py 70-115 ===")
for i in range(69, min(115, len(лн))):
    print("  %4d| %s" % (i + 1, лн[i][:100]))
