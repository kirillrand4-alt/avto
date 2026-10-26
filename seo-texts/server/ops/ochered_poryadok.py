# -*- coding: utf-8 -*-
"""Голова очереди автоотправки ровно запросом claim_approved_due (без захвата). Только чтение."""
import sqlite3
from collections import Counter
from datetime import datetime, timezone
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
now = datetime.now(timezone.utc).isoformat()
print("now_iso:", now)
ряды = c.execute("""SELECT m.id, m.campaign_id, m.scheduled_at FROM messages m
    WHERE m.status='scheduled' AND m.scheduled_at <= ?
      AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')
    ORDER BY m.scheduled_at, m.id""", (now,)).fetchall()
print("всего в выборке:", len(ряды), Counter(кам.get(r[1]) for r in ряды))
for r in ряды[:8]:
    print(" ", r[0], кам.get(r[1]), r[2])
кц = [r for r in ряды if "meyer" not in str(кам.get(r[1])).lower()]
print("первое КЦ на позиции:", next((i for i, r in enumerate(ряды) if "meyer" not in str(кам.get(r[1])).lower()), None), кц[:3])
print("формат scheduled_at КЦ (пример):", c.execute("SELECT scheduled_at FROM messages WHERE campaign_id=17 AND status='scheduled' LIMIT 3").fetchall())
