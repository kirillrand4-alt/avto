# -*- coding: utf-8 -*-
"""Сбои предклассификатора в разрезе моделей — сводка последней строкой."""
import glob
import io
import os
import re
from collections import Counter

п = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
           key=os.path.getmtime, reverse=True)[0]
с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
по_модели, по_виду = Counter(), Counter()
for x in с:
    if "споткнулся" not in x:
        continue
    m = re.search(r"споткнулся на ([\w.\-]+)", x)
    if m:
        по_модели[m.group(1)] += 1
    вид = re.sub(r"\d+", "N", x.split(":", 2)[-1]).strip()
    по_виду[вид[:90]] += 1
всего_пачек = sum(1 for x in с if "не ответил ни одной моделью" in x)
письма = sum(1 for x in с if re.match(r"\s*\[\d+/\d+\]", x))
print("=== СБОИ ПО МОДЕЛЯМ ===")
for м, n in по_модели.most_common():
    print("   %-24s %4d" % (м, n))
print("\n=== ПО ВИДУ ОШИБКИ ===")
for в, n in по_виду.most_common(6):
    print("   %4d  %s" % (n, в))
print("\n=== ИТОГ ===")
print("лог: %s, строк %d" % (os.path.basename(п), len(с)))
print("пачек без вердикта: %d; писем в логе: %d" % (всего_пачек, письма))
