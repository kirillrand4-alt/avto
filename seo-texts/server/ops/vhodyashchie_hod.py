# -*- coding: utf-8 -*-
"""Входящие: когда приходили (event_ts) и когда записаны (created_at) за сегодня по 30 минут. Только чтение."""
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
ТИПЫ = "('reply','reply_auto','other','bounce','dsn','complaint','reject_spam')"
print("последнее записанное входящее:", c.execute("SELECT MAX(created_at), MAX(event_ts) FROM events WHERE event_type IN %s" % ТИПЫ).fetchone())
сч = Counter()
for ts, cr in c.execute("SELECT event_ts, created_at FROM events WHERE event_type IN %s AND created_at >= date('now')" % ТИПЫ):
    сч[cr[11:13] + ":" + ("00" if cr[14:16] < "30" else "30")] += 1
print("записано входящих по получасам (UTC):", sorted(сч.items()))
задержка = [r for r in c.execute("SELECT id, event_type, event_ts, created_at FROM events WHERE event_type IN %s "
                                 "AND created_at >= datetime('now','-90 minutes') ORDER BY id DESC LIMIT 12" % ТИПЫ)]
for r in задержка:
    print(" ", r)
