# -*- coding: utf-8 -*-
"""Время отправки у живых писем по кампаниям: есть ли scheduled_at, в прошлом/будущем, по дням. Только чтение."""
import sqlite3
from collections import Counter
from datetime import datetime
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сейчас = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
сч, дни = Counter(), Counter()
for cid, st, sa in c.execute("SELECT campaign_id, status, scheduled_at FROM messages WHERE status IN ('pending_review','approved','scheduled','sending')"):
    k = кам.get(cid, cid)
    if not sa: в = "без времени"
    elif str(sa).replace(" ", "T") < сейчас: в = "время прошло"
    else: в = "время впереди"; дни[(k, str(sa)[:10])] += 1
    сч[(k, st, в)] += 1
for k, v in sorted(сч.items()): print(v, k)
print("--- по дням (впереди):")
for k, v in sorted(дни.items()): print(v, k)
