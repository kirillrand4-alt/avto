# -*- coding: utf-8 -*-
"""Как выглядит расписание scheduled: ящик задан ли, сколько разных времён, примеры."""
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db")
р = c.execute("SELECT m.mailbox_id, m.scheduled_at, r.tz FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='scheduled'").fetchall()
print("всего", len(р), "без ящика", sum(1 for x in р if not x[0]), "разных времён", len({x[1] for x in р}))
print("ящики:", Counter(x[0] for x in р).most_common(5))
print("пояса:", Counter(x[2] for x in р).most_common(8))
print("времена:", Counter(str(x[1])[:16] for x in р).most_common(8))
print("мин/макс:", min(str(x[1]) for x in р), max(str(x[1]) for x in р))
