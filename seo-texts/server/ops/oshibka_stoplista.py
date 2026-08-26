# -*- coding: utf-8 -*-
"""Полная трасса ошибки «адрес не лёг в стоп-лист»."""
import io
import os

п = r"C:\sender\_ops\panel_err.log"
строки = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
места = [i for i, с in enumerate(строки) if "не лёг в стоп-лист" in с]
print("вхождений: %d" % len(места))
if места:
    i = места[-1]
    print("=== последняя трасса ===")
    for с in строки[i:i + 22]:
        print("   " + с[:200])
    print("")
    print("=== первая по времени ===")
    j = места[0]
    for с in строки[max(0, j - 2):j + 6]:
        print("   " + с[:200])
