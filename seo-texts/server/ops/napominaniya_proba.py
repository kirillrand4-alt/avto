# -*- coding: utf-8 -*-
"""Вердикты пробы у адресов пилота напоминаний: по отправленным и ещё ждущим. Только чтение."""
import io
import json
import sqlite3
import sys
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
проба = {r[0].lower(): (r[1], r[2]) for r in c.execute("SELECT email, verdict, checked_at FROM addr_probe")} if False else {}
cols = [r[1] for r in c.execute("PRAGMA table_info(addr_probe)")]
тс = "checked_at" if "checked_at" in cols else ("ts" if "ts" in cols else None)
for r in c.execute("SELECT email, verdict%s FROM addr_probe" % ((", " + тс) if тс else "")):
    проба[r[0].lower()] = (r[1], r[2] if тс else "")
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")]
сч = Counter()
без = []
for x in з:
    ст = c.execute("SELECT status FROM confirm_reviews WHERE id=?", (x["karta"],)).fetchone()[0]
    в = проба.get(x["email"].lower(), ("нет вердикта", ""))[0]
    сч[(ст, в)] += 1
    if в == "нет вердикта" and ст == "pending":
        без.append(x["email"])
for k, n in sorted(сч.items()):
    print("%-10s %-16s %d" % (k[0], k[1], n))
for a in sys.argv[1:]:
    print(a, проба.get(a.lower()))
print("pending без вердикта:", len(без))
