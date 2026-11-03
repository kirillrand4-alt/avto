# -*- coding: utf-8 -*-
"""Счёт напоминаний по статусу и дню отправки."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for r in c.execute("SELECT status, substr(COALESCE(decided_at,''),1,10) d, COUNT(*), COUNT(DISTINCT inn) FROM confirm_reviews "
                   "WHERE kind='reply' AND panel_json LIKE '%napominanie%' GROUP BY 1,2 ORDER BY 2,1"):
    print(r)
