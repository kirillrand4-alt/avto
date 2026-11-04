# -*- coding: utf-8 -*-
"""Что ждёт отправки (scheduled/sending): по кампании и ящику-пулу; сколько ушло сегодня с ящиков Meyer."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for r in c.execute("SELECT c.name, m.status, COUNT(*), MIN(m.scheduled_at) FROM messages m LEFT JOIN campaigns c ON c.id=m.campaign_id "
                   "WHERE m.status IN ('scheduled','sending','queued') GROUP BY 1,2 ORDER BY 3 DESC"):
    print(tuple(r))
