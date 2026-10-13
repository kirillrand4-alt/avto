# -*- coding: utf-8 -*-
"""Строки лога 9000 перед последним стартом (чем закончился прошлый прогон)."""
import io
стр = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8", errors="replace").read().splitlines()
старты = [i for i, с in enumerate(стр) if "[1/" in с]
print("стартов в логе: %d, строк %d" % (len(старты), len(стр)))
if len(старты) >= 1:
    i = старты[-1]
    for с in стр[max(0, i - 25):i + 1]:
        print(с[:230])
print("=== ЛОГ ПЕРЕД СТАРТОМ ===")
