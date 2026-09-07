# -*- coding: utf-8 -*-
"""Почему 221 получатель считается «уже есть»: под каким источником они лежат."""
import sqlite3, sys, io, json, re
from collections import Counter
sys.path.insert(0, r"C:\sender")
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
ж = r"C:\sender\_ops\agro-zalito.jsonl"
инн_журнала = set()
try:
    for с in io.open(ж, encoding="utf-8", errors="replace"):
        с = с.strip()
        if с:
            try:
                инн_журнала.add(str(json.loads(с).get("inn") or ""))
            except Exception:
                pass
except IOError:
    pass
ист = Counter()
для_журнала = Counter()
for и, s, g in c.execute("SELECT inn, source, created_at FROM recipients WHERE inn IS NOT NULL"):
    if str(и) in инн_журнала:
        для_журнала[str(s or "")] += 1
    ист[str(s or "")] += 1
print("=" * 70)
print("=== КТО ЭТИ 221 ===")
print("строк в agro-zalito.jsonl (наши, залитые до срыва): %d" % len(инн_журнала))
print("их источник в recipients:")
for k, v in для_журнала.most_common(10):
    print("   %-30s %6d" % (k or "(пусто)", v))
print("")
print("всего источников в recipients (топ-8):")
for k, v in ист.most_common(8):
    print("   %-30s %6d" % (k or "(пусто)", v))
