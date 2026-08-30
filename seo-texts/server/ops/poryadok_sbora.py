# -*- coding: utf-8 -*-
"""Порядок кодов в задании и что уже собрано — по факту."""
import csv
import io
import os
from collections import Counter

КОДЫ = r"C:\seostat\Parser2\data\okved-agro.txt"
CSV = r"C:\seostat\Parser2\data\agro-base.csv"
МЕЙЕР = ("01.", "10.", "46.21", "46.3", "46.37", "46.38", "46.39", "46.6",
         "46.9", "52.10", "11.")
список = [с.strip() for с in io.open(КОДЫ, encoding="utf-8") if с.strip()]
print("кодов в файле: %d" % len(список))
print("первые 20 в порядке обработки: %s" % ", ".join(список[:20]))
print("последние 12:                  %s" % ", ".join(список[-12:]))
мейер = [к for к in список if к.startswith(МЕЙЕР)]
прочие = [к for к in список if not к.startswith(МЕЙЕР)]
print("\nиз них профиль Meyer (сельхоз, пищёвка, пищевой опт): %d" % len(мейер))
print("прочие (не мейеровские): %d — %s" % (len(прочие), ", ".join(прочие)))
где = [i + 1 for i, к in enumerate(список) if not к.startswith(МЕЙЕР)]
print("их позиции в файле: %s" % (где[:20] if где else "—"))

if not os.path.exists(CSV):
    print("\nCSV ещё нет")
    raise SystemExit(0)
по_коду = Counter()
строк = 0
with io.open(CSV, encoding="utf-8", errors="ignore", newline="") as f:
    # Разделитель в выгрузке Parser2 — ТОЧКА С ЗАПЯТОЙ. С запятой строка не
    # бьётся вовсе, и разбивка по кодам выходила мусором: каждая строка
    # считалась отдельным «кодом» вида «0101004604;1».
    ч = csv.reader(f, delimiter=";")
    шапка = next(ч, [])
    поле = None
    for i, имя in enumerate(шапка):
        if "оквэд" in имя.lower() or "okved" in имя.lower():
            поле = i
            break
    for ряд in ч:
        строк += 1
        if поле is not None and поле < len(ряд):
            з = str(ряд[поле] or "").strip()
            по_коду[з.split()[0] if з else "—"] += 1
print("\nсобрано строк: %d" % строк)
print("шапка CSV: %s" % ", ".join(шапка[:12]))
print("\nпо кодам (топ-15):")
for к, n in по_коду.most_common(15):
    print("   %-12s %6d" % (к[:12], n))
