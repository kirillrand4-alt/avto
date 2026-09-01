# -*- coding: utf-8 -*-
"""Двадцать самых крупных кодов сбора — печатаем В КОНЦЕ."""
import csv
import io
from collections import Counter

CSV = r"C:\seostat\Parser2\data\agro-base.csv"
коды, имена = Counter(), {}
всего = 0
with io.open(CSV, encoding="utf-8-sig", errors="replace", newline="") as ф:
    for р in csv.DictReader(ф, delimiter=";"):
        всего += 1
        к = str(р.get("Основной ОКВЭД") or "").strip() or "(пусто)"
        коды[к] += 1
        имена.setdefault(к, str(р.get("Вид деятельности") or "").strip())

print("=" * 72)
print("=== ДВАДЦАТЬ САМЫХ КРУПНЫХ КОДОВ СБОРА (всего %d компаний) ===" % всего)
for к, н in коды.most_common(20):
    доля = 100.0 * н / всего
    print("   %-10s %7d (%4.1f%%)  %s" % (к, н, доля, имена.get(к, "")[:78]))
верх = sum(н for _, н in коды.most_common(20))
print("")
print("на эти двадцать кодов приходится %d из %d компаний (%.0f%%)"
      % (верх, всего, 100.0 * верх / всего))
