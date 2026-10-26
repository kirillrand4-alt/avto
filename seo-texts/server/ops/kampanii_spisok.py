# -*- coding: utf-8 -*-
"""Кампании: id, имя, писем по статусам. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for cid, имя in c.execute("SELECT id, name FROM campaigns ORDER BY id"):
    ст = dict(c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id=? GROUP BY status", (cid,)).fetchall())
    print(cid, имя, ст)
