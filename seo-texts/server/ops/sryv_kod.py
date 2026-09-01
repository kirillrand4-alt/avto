# -*- coding: utf-8 -*-
"""Точное место, где рождается «срыв в рассуждение даже на low»."""
import io
import re

П = r"C:\sender\sender\review_lenses.py"
s = io.open(П, encoding="utf-8", errors="replace").read()
строки = s.splitlines()
for i, стр in enumerate(строки):
    if "срыв в рассуждение" in стр or "срыв в" in стр:
        а, б = max(0, i - 45), min(len(строки), i + 22)
        print("=== строки %d-%d ===" % (а + 1, б))
        for j in range(а, б):
            print("%5d| %s" % (j + 1, строки[j][:160]))
        print("")
