# -*- coding: utf-8 -*-
"""События за сегодня по типам (жалобы, отбои, ответы, отписки) и отчёты DMARC."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
for т, n in c.execute("SELECT event_type, count(*) FROM events WHERE created_at >= date('now') GROUP BY 1 ORDER BY 2 DESC"):
    print("   %-24s %d" % (т, n))
n = c.execute("SELECT count(*) FROM events WHERE created_at >= date('now','-3 days') AND "
              "(detail_json LIKE '%dmarc%' OR detail_json LIKE '%Report Domain%')").fetchone()[0]
print("писем-отчётов DMARC за 3 дня: %d" % n)
print("=== СОБЫТИЯ СЕГОДНЯ ===")
