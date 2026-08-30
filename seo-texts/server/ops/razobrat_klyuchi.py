# -*- coding: utf-8 -*-
"""Что на самом деле лежит в api_keys.txt: форма ключей и сколько мусора."""
import io
import os
import re
import sys
from collections import Counter

КОРЕНЬ = r"C:\seostat\Parser2"
sys.path.insert(0, КОРЕНЬ)
ФАЙЛ = os.path.join(КОРЕНЬ, "data", "api_keys.txt")
from metalparser.checko import read_keys_file, _parse_keys   # noqa: E402

сырое = read_keys_file(ФАЙЛ)
ключи = list(dict.fromkeys(_parse_keys(сырое)))
дл = Counter(len(к) for к in ключи)
print("=== ДЛИНЫ РАЗОБРАННОГО ===")
for д in sorted(дл):
    латиница = sum(1 for к in ключи
                   if len(к) == д and re.fullmatch(r"[A-Za-z0-9]+", к))
    print("   длина %2d: всего %3d, из них латиница+цифры %3d" % (д, дл[д], латиница))

годные = [к for к in ключи if re.fullmatch(r"[A-Za-z0-9]{28,40}", к)]
print("\nпохоже на настоящие ключи (латиница/цифры, 28–40): %d" % len(годные))
print("их длины: %s" % sorted(Counter(len(к) for к in годные).items()))

print("\n=== ЧТО ЕЩЁ РАЗБОР СЧИТАЕТ КЛЮЧОМ (первые 20 не-годных) ===")
мусор = [к for к in ключи if к not in set(годные)]
for к in мусор[:20]:
    print("   %r" % к[:44])
print("   … всего мусора: %d" % len(мусор))

print("\n=== ИСХОДНЫЙ ФАЙЛ: первые 12 строк ===")
for i, с in enumerate(io.open(ФАЙЛ, encoding="utf-8", errors="replace")):
    if i >= 12:
        break
    print("   %s" % с.rstrip()[:120])
