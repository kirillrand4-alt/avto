# -*- coding: utf-8 -*-
"""Есть ли в базе событие/лид от этих адресов (только чтение). Аргументы: адреса."""
import sqlite3, sys
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
ev = [r[1] for r in c.execute("PRAGMA table_info(events)")]
for a in sys.argv[1:]:
    кол = [k for k in ("from_addr", "sender", "email", "from_email") if k in ev]
    e = []
    for k in кол:
        e += c.execute("SELECT event_type, event_ts FROM events WHERE lower(%s) LIKE ? ORDER BY event_ts DESC LIMIT 3" % k, ("%" + a.lower() + "%",)).fetchall()
    l = c.execute("SELECT id, status, created_at FROM leads WHERE lower(email)=?", (a.lower(),)).fetchall()
    print(a, "| события:", e, "| лиды:", l)
print("колонки events:", ev)
