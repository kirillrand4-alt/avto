# -*- coding: utf-8 -*-
"""Какие ключи лежат в журнале генерации — чтобы резюм читал их правильно."""
import json
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ключи, этапы = Counter(), Counter()
примеры = {}
n = 0
with open(ЖУРНАЛ, "r", encoding="utf-8", errors="replace") as ф:
    for стр in ф:
        стр = стр.strip()
        if not стр:
            continue
        try:
            з = json.loads(стр)
        except Exception:  # noqa: BLE001
            continue
        n += 1
        for к in з:
            ключи[к] += 1
        э = str(з.get("этап") or з.get("stage") or "?")
        этапы[э] += 1
        if э not in примеры:
            примеры[э] = {к: (str(v)[:40] if not isinstance(v, (int, float))
                              else v) for к, v in з.items()}
print("записей: %d" % n)
print("")
print("=== КЛЮЧИ ===")
for к, в in ключи.most_common(40):
    print("   %-24s %7d" % (к, в))
print("")
print("=== ЭТАПЫ ===")
for к, в in этапы.most_common(20):
    print("   %-24s %7d" % (к, в))
print("")
print("=== ПРИМЕР КАЖДОГО ЭТАПА ===")
for э, пр in list(примеры.items())[:8]:
    print("--- %s ---" % э)
    for к, v in list(пр.items())[:14]:
        print("      %-20s %s" % (к, v))
