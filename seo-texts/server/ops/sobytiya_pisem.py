# -*- coding: utf-8 -*-
"""События по письмам: sobytiya_pisem.py id,id. Только чтение."""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for i in sys.argv[1].split(","):
    print(i, c.execute("SELECT event_type, substr(event_ts,1,16), substr(coalesce(detail_json,\"\"),1,90) FROM events WHERE message_id=? ORDER BY id", (int(i),)).fetchall())
