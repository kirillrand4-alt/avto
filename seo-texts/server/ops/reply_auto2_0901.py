# -*- coding: utf-8 -*-
"""Только чтение: главное последним."""
import glob
import io
import os
import sqlite3
import sys

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ГДЕ КЛАССИФИЦИРУЕТСЯ АВТООТВЕТ ===")
for ф in glob.glob(r"C:\sender\sender\*.py"):
    try:
        стр = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        continue
    for i, x in enumerate(стр):
        if "reply_auto" in x and ("=" in x or "return" in x or "type" in x.lower()):
            print("  %-18s:%-5d %s" % (os.path.basename(ф), i + 1, x.strip()[:92]))

print("\n=== КОНСТАНТЫ ===")
sys.path.insert(0, r"C:\sender")
for мод in ("sender.analytics",):
    m = __import__(мод, fromlist=["*"])
    for имя in dir(m):
        if "REPLY" in имя or "EVENT" in имя:
            print("  %s = %r" % (имя, getattr(m, имя)))

print("\n=== ИТОГ: reply И reply_auto ПО ДНЯМ ===")
д = {}
for р in s.execute("SELECT substr(created_at,1,10) d, event_type t, COUNT(*) n"
                   " FROM events WHERE event_type IN ('reply','reply_auto')"
                   " GROUP BY d, t ORDER BY d"):
    д.setdefault(р["d"], {})[р["t"]] = р["n"]
print("  %-12s %8s %12s" % ("день", "reply", "reply_auto"))
for k in sorted(д):
    print("  %-12s %8d %12d" % (k, д[k].get("reply", 0), д[k].get("reply_auto", 0)))
print("\n  первое reply_auto: %s"
      % s.execute("SELECT MIN(created_at) m FROM events WHERE event_type='reply_auto'"
                  ).fetchone()["m"])
print("  последнее reply   : %s"
      % s.execute("SELECT MAX(created_at) m FROM events WHERE event_type='reply'"
                  ).fetchone()["m"])
