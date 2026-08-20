# -*- coding: utf-8 -*-
"""Первая строка письма: есть ли обращение по имени."""
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for rid in [int(a) for a in sys.argv[1:] if a.isdigit()]:
    r = c.execute("SELECT id, email, COALESCE(body,'') b FROM confirm_reviews "
                  "WHERE id=?", (rid,)).fetchone()
    if not r:
        continue
    первая = str(r["b"]).split("\n", 1)[0]
    print(f"  #{rid} {r['email']:<32} -> {первая!r}")
