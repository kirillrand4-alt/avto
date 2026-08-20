# -*- coding: utf-8 -*-
"""Хвосты писем-копий: куда вставлять оговорку о том, что коллеге уже писали."""
import sqlite3
import sys

ИДЫ = [int(a) for a in sys.argv[1:] if a.isdigit()]
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for rid in ИДЫ:
    r = c.execute("SELECT id, email, body FROM confirm_reviews WHERE id=?",
                  (rid,)).fetchone()
    if not r:
        continue
    т = str(r["body"] or "")
    print("=" * 70)
    print(f"#{rid} {r['email']}")
    print("...последние 420 знаков...")
    print(т[-420:])
