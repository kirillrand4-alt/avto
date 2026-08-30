# -*- coding: utf-8 -*-
"""Что заполнено в собранном CSV: по каждой колонке — сколько непустых."""
import csv
import io
import os
from collections import Counter

CSV = r"C:\seostat\Parser2\data\agro-base.csv"
if not os.path.exists(CSV):
    print("файла нет")
    raise SystemExit(0)
непустые = Counter()
всего = 0
коды = Counter()
регионы = Counter()
примеры = []
with io.open(CSV, encoding="utf-8-sig", errors="ignore", newline="") as f:
    ч = csv.DictReader(f, delimiter=";")
    поля = ч.fieldnames or []
    for ряд in ч:
        всего += 1
        for к in поля:
            if str(ряд.get(к) or "").strip():
                непустые[к] += 1
        о = str(ряд.get("Основной ОКВЭД") or "").strip()
        коды[о.split()[0] if о else "—"] += 1
        регионы[str(ряд.get("Регион") or "—").strip()[:28]] += 1
        if len(примеры) < 2:
            примеры.append(ряд)
print("строк: %d" % всего)
print("\n%-22s %9s %7s" % ("колонка", "непустых", "доля"))
for к in поля:
    n = непустые[к]
    print("%-22s %9d %6.1f%%" % (к, n, 100.0 * n / всего if всего else 0))
print("\nтоп кодов: %s"
      % ", ".join("%s=%d" % кv for кv in коды.most_common(8)))
print("топ регионов: %s"
      % ", ".join("%s=%d" % кv for кv in регионы.most_common(6)))
print("\nпример записи:")
for к, v in (примеры[0] if примеры else {}).items():
    print("   %-22s %s" % (к, str(v)[:70]))
