# -*- coding: utf-8 -*-
"""Полный текст события (входящего): sobytie_polnoe.py <event_id>. Только чтение."""
import json
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
е = c.execute("SELECT * FROM events WHERE id=?", (int(sys.argv[1]),)).fetchone()
print({k: е[k] for k in е.keys() if k != "detail_json"})
d = json.loads(е["detail_json"] or "{}")
h = d.get("headers") or {}
for k in ("From", "To", "Cc", "Subject", "Date", "In-Reply-To", "References"):
    if h.get(k):
        print("%s: %s" % (k, str(h[k])[:300]))
тело = d.get("body") or d.get("text") or ""
if not тело:
    for k, v in d.items():
        if isinstance(v, str) and len(v) > len(тело) and k != "headers":
            тело = v
print("\nключи:", list(d.keys()))
print("\n" + тело[:6000])
