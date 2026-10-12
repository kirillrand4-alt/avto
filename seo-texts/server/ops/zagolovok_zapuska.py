# -*- coding: utf-8 -*-
"""Шапка последнего запуска 9000 целиком — до первого письма (кто и почему снят)."""
import io
т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8", errors="replace").read()
кусок = "==== ЗАПУСК" + т.rsplit("==== ЗАПУСК", 1)[-1]
for с in кусок.splitlines():
    if "/" in с and "] " in с and ("ОК" in с or "брак" in с):
        break
    print(с[:200])
print("=== ШАПКА ===")
