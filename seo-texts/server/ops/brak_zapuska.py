# -*- coding: utf-8 -*-
"""Причины брака последнего запуска «Россия 9000» — по логу."""
import io
import re
from collections import Counter
т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8",
            errors="replace").read().rsplit("==== ЗАПУСК", 1)[-1]
прич = Counter()
примеры = {}
отрасль = Counter()
for с in т.splitlines():
    if "] брак" not in с:
        continue
    хвост = с.split("|", 1)[1].strip() if "|" in с else ""
    ключ = re.split(r"[:(«]", хвост, 1)[0].strip()[:50] or "(нет причины)"
    прич[ключ] += 1
    примеры.setdefault(ключ, хвост[:170])
for к, n in прич.most_common(14):
    print("%4d  %s" % (n, к))
print("--- примеры ---")
for к, _ in прич.most_common(7):
    print("   [%s] %s" % (к[:30], примеры[к]))
print("=== БРАК ЗАПУСКА ===")
