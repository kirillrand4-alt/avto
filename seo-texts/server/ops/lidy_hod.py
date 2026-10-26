# -*- coding: utf-8 -*-
"""Лиды и ответы по дням: сколько ответов пришло и сколько лидов заведено. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for д in c.execute("SELECT DISTINCT substr(event_ts,1,10) FROM events WHERE event_ts >= date('now','-6 days') ORDER BY 1").fetchall():
    д = д[0]
    отв = c.execute("SELECT COUNT(*) FROM events WHERE event_type='reply' AND substr(event_ts,1,10)=?", (д,)).fetchone()[0]
    авто = c.execute("SELECT COUNT(*) FROM events WHERE event_type='reply_auto' AND substr(event_ts,1,10)=?", (д,)).fetchone()[0]
    лиды = c.execute("SELECT COUNT(*) FROM leads WHERE substr(created_at,1,10)=?", (д,)).fetchone()[0]
    print(д, "ответов", отв, "автоответов", авто, "лидов заведено", лиды)
print("последний лид:", c.execute("SELECT id, created_at, email, reply_kind FROM leads ORDER BY id DESC LIMIT 3").fetchall())
