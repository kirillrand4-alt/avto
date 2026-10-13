# -*- coding: utf-8 -*-
"""Итог последнего запуска 9000 по логу (годится и для оборванного)."""
import io
import re
т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8", errors="replace").read()
кусок = т.rsplit("==== ЗАПУСК", 1)[-1]
ок = брак = 0
деньги = 0.0
for с in кусок.splitlines():
    м = re.search(r"\[\d+/\d+\]\s+(ОК|брак)\s.*?\s(\d+)с \$([\d.]+)", с)
    if not м:
        continue
    деньги += float(м.group(3))
    if м.group(1) == "ОК":
        ок += 1
    else:
        брак += 1
print("запуск%s" % кусок.splitlines()[0][:60])
print("попыток %d, годных %d, брак %d, потрачено $%.2f, за годное $%.3f"
      % (ок + брак, ок, брак, деньги, деньги / ок if ок else 0))
print("=== ИТОГ ЗАПУСКА ===")
