# -*- coding: utf-8 -*-
"""Что лежит в очереди подтверждения по кампании 14 и когда легло."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
for р in c.execute("SELECT status, COUNT(*), MIN(created_at), MAX(created_at) "
                   "FROM confirm_reviews WHERE campaign_id=14 GROUP BY status"):
    print("   %-10s %4d  с %s по %s" % (р[0], р[1], str(р[2])[:16], str(р[3])[:16]))
print("=== ОЧЕРЕДЬ 14 ===")
