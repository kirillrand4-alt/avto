# -*- coding: utf-8 -*-
"""Пояс и регион получателей писем: tz_poluchatelya.py id,id. Только чтение."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for i in sys.argv[1].split(","):
    print(c.execute("SELECT m.id, r.id, r.tz, r.region, r.email, substr(r.extra_json,1,200) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.id=?", (int(i),)).fetchone())
