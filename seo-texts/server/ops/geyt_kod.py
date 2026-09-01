# -*- coding: utf-8 -*-
"""Код target_gate вокруг сборки промпта и разбора ответа."""
import io
t = io.open(r"C:\sender\sender\target_gate.py", encoding="utf-8",
            errors="replace").read().splitlines()
for i, стр in enumerate(t):
    if "блоки" in стр or "def " in стр and "self" in стр:
        pass
а, б = 230, 345
print("=== target_gate.py %d-%d ===" % (а + 1, б))
for j in range(а, min(б, len(t))):
    print("%5d| %s" % (j + 1, t[j][:150]))
