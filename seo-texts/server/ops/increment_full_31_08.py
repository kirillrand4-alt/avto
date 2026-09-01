# -*- coding: utf-8 -*-
"""Только чтение: increment_sent целиком."""
import io
import re

стр = io.open(r"C:\sender\sender\store.py", encoding="utf-8",
              errors="replace").read().splitlines()
н = [i for i, x in enumerate(стр) if re.match(r"\s*def increment_sent", x)]
print("=== найдено: %s ===" % [i + 1 for i in н])
for i in н:
    for j in range(i, min(i + 60, len(стр))):
        print("  %4d  %s" % (j + 1, стр[j][:112]))
