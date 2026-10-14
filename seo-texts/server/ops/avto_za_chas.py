# -*- coding: utf-8 -*-
"""Что ушло в автоотправку (bulk-to-auto) за последние часы и сколько в расписании."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
print("bulk-to-auto по часам:", c.execute("SELECT substr(decided_at,1,13), campaign_id, count(*) FROM confirm_reviews "
      "WHERE reason='bulk-to-auto' AND decided_at >= datetime('now','-12 hours') GROUP BY 1,2 ORDER BY 1").fetchall())
print("messages scheduled по кампаниям:", c.execute("SELECT campaign_id, count(*) FROM messages WHERE status='scheduled' GROUP BY 1").fetchall())
print("сейчас UTC:", c.execute("SELECT datetime('now')").fetchone())
print("=== АВТО ЗА ЧАС ===")
