# -*- coding: utf-8 -*-
"""Входящие (ответы/отбивки) и отправки по часам за сегодня (UTC) — работал ли сбор почты. Только чтение."""
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
print("входящие по часам:", c.execute("SELECT substr(created_at,1,13), event_type, COUNT(*) FROM events WHERE created_at>='2026-11-13' AND event_type IN ('reply','reply_auto','bounce','other','complaint') GROUP BY 1,2").fetchall())
print("последнее входящее:", c.execute("SELECT MAX(created_at) FROM events WHERE event_type IN ('reply','reply_auto','bounce','other')").fetchone())
print("отправки по часам:", c.execute("SELECT substr(sent_at,1,13), COUNT(*) FROM messages WHERE status='sent' AND sent_at>='2026-11-13' GROUP BY 1").fetchall())
