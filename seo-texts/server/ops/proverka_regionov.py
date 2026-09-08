# -*- coding: utf-8 -*-
"""Все обороты про регион, которые сейчас стоят в письмах партии."""
import re, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.store import Store                                  # noqa: E402
import varianty_pisma as V                                      # noqa: E402

ФРАЗА = re.compile(r"(выращивает|растит|работает с) зерновые[^,.]*")
store = Store(r"C:\sender\sender.db")
с = Counter()
with store._lock:
    for р in store._conn.execute(
            "SELECT body FROM confirm_reviews WHERE subject IN (%s)"
            % ",".join("?" * len(V.ТЕМЫ)), tuple(V.ТЕМЫ)):
        м = ФРАЗА.search(str(р["body"] or ""))
        if м:
            хвост = м.group(0).split("зерновые", 1)[1].strip()
            с[хвост or "(без региона)"] += 1
for к, в in с.most_common(40):
    print("   %-46s %5d" % (к, в))
print("")
print("=" * 70)
print("=== ОБОРОТЫ ПРО РЕГИОН В ЖИВЫХ ПИСЬМАХ ===")
print("разных: %d; писем: %d" % (len(с), sum(с.values())))
