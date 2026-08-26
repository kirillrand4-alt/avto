# -*- coding: utf-8 -*-
"""Успел ли просев что-то проставить в базу, и сколько осудил."""
import io
import json
import os
import sqlite3
from collections import Counter

ж = r"C:\sender\_ops\predprosev-meyer.jsonl"
свод = Counter()
строк = 0
if os.path.exists(ж):
    for с in io.open(ж, encoding="utf-8", errors="replace"):
        try:
            з = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        строк += 1
        свод[з.get("вердикт")] += 1
print("журнал вердиктов: %d строк, раскладка %s" % (строк, dict(свод)))

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
n1 = c.execute("SELECT COUNT(*) FROM recipients "
               "WHERE extra_json LIKE '%ai_division_pochemu%'").fetchone()[0]
n2 = c.execute("SELECT COUNT(*) FROM recipients "
               "WHERE extra_json LIKE '%ne_nash_ni_odnomu%'").fetchone()[0]
print("в базе проставлено: ai_division_pochemu=%d, ne_nash_ni_odnomu=%d" % (n1, n2))
c.close()
