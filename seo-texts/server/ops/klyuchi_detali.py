# -*- coding: utf-8 -*-
"""Что реально лежит в detail_json у каждого типа события.

Ярлыки и причины для ленты надо строить по фактическим ключам, а не по
догадке: иначе «за что отбивка» окажется пустым столбцом.
"""
import json
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
ключи = defaultdict(Counter)
примеры = {}
for р in c.execute("SELECT event_type, detail_json FROM events "
                   " ORDER BY id DESC LIMIT 4000"):
    try:
        d = json.loads(р["detail_json"] or "{}")
    except Exception:  # noqa: BLE001
        continue
    if not isinstance(d, dict):
        continue
    for к in d:
        ключи[р["event_type"]][к] += 1
    if р["event_type"] not in примеры and d:
        примеры[р["event_type"]] = d

for т in sorted(ключи):
    print("\n=== %s ===" % т)
    print("   ключи: %s" % ", ".join("%s×%d" % (к, н)
                                     for к, н in ключи[т].most_common(8)))
    п = примеры.get(т) or {}
    for к, з in list(п.items())[:5]:
        print("      %-16s %s" % (к, str(з).replace("\n", " ")[:96]))
