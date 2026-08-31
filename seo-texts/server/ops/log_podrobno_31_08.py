# -*- coding: utf-8 -*-
"""Только чтение: разбор строк прогона по [N/M]. Итог последним (§8.10)."""
import glob
import io
import os
import re
import datetime
from collections import Counter

логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)
л = логи[0]
стр = io.open(л, encoding="utf-8", errors="replace").read().splitlines()
письма = [x for x in стр if re.match(r"\s*\[\d+/\d+\]", x)]
ок = [x for x in письма if re.search(r"\]\s*ОК", x)]
брак = [x for x in письма if re.search(r"\]\s*брак", x)]
print("=== ПОСЛЕДНИЕ 12 СТРОК-ПИСЕМ ===")
for x in письма[-12:]:
    print("  " + x.strip()[:165])

прич = Counter()
for x in брак:
    m = re.search(r"\|\s*(.+)$", x)
    if m:
        прич[m.group(1).strip()[:70]] += 1
print("\n=== ПРИЧИНЫ БРАКА ===")
for k, v in прич.most_common(10):
    print("  %3d  %s" % (v, k))

цены = [float(m.group(1)) for x in письма
        for m in [re.search(r"\$([0-9.]+)", x)] if m]
print("\n=== ИТОГ ===")
print("  писем в логе: %d | ОК: %d | брак: %d" % (len(письма), len(ок), len(брак)))
if письма:
    print("  отдача пока: %.0f%%" % (100.0 * len(ок) / len(письма)))
if цены:
    print("  потрачено в этих строках: $%.2f" % sum(цены))
    if ок:
        print("  на годное письмо: $%.3f" % (sum(цены) / len(ок)))
отказы = sum(1 for x in брак if "нет JSON" in x)
print("  из них ОТКАЗОВ МОДЕЛИ (нет JSON): %d" % отказы)
print("  лог изменён: %s, сейчас %s"
      % (datetime.datetime.fromtimestamp(os.path.getmtime(л)).strftime("%H:%M:%S"),
         datetime.datetime.now().strftime("%H:%M:%S")))
