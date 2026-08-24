# -*- coding: utf-8 -*-
"""Кто заполняет поле na_podtverzhdenii, которое рисует виджет."""
import io
import os
import re

for корень, _, имена in os.walk(r"C:\sender\sender"):
    if "__pycache__" in корень or "tests" in корень:
        continue
    for имя in имена:
        if not имя.endswith(".py") or ".bak" in имя:
            continue
        п = os.path.join(корень, имя)
        try:
            т = io.open(п, encoding="utf-8").read()
        except Exception:  # noqa: BLE001
            continue
        if "na_podtverzhdenii" not in т:
            continue
        строки = т.split("\n")
        for н, с in enumerate(строки, 1):
            if "na_podtverzhdenii" in с:
                print("=== %s:%d ===" % (имя, н))
                for k in range(max(0, н - 14), min(len(строки), н + 4)):
                    метка = ">>" if k == н - 1 else "  "
                    print("  %s %-5d %s" % (метка, k + 1, строки[k][:140]))
                print()
