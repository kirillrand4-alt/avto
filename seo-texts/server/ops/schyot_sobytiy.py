# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
print("событий всего: %d" % c.execute("SELECT COUNT(*) FROM events").fetchone()[0])
print("последнее: %s" % c.execute("SELECT MAX(created_at) FROM events").fetchone()[0])
print("создано за последние 15 мин: %d" % c.execute(
    "SELECT COUNT(*) FROM events WHERE created_at > datetime('now','-15 minutes')"
).fetchone()[0])
c.close()
