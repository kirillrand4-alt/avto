# -*- coding: utf-8 -*-
"""Сколько ушло сегодня (UTC-сутки) с каждого ящика: письма messages, по кампании; сравнить с лимитом панели."""
import collections, sqlite3
from datetime import datetime, timezone
д = datetime.now(timezone.utc).strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
по = collections.defaultdict(collections.Counter)
for mb, n, s in c.execute("SELECT m.mailbox_id, c.name, m.subject FROM messages m LEFT JOIN campaigns c ON c.id=m.campaign_id WHERE m.status='sent' AND substr(m.sent_at,1,10)=?", (д,)):
    по[mb]["Re" if (s or "").startswith("Re:") else "новое"] += 1
cols = [r[1] for r in c.execute("PRAGMA table_info(mailbox_state)")] if c.execute("SELECT name FROM sqlite_master WHERE name='mailbox_state'").fetchone() else []
print("колонки mailbox_state:", cols)
for mb, сч in sorted(по.items()):
    print("%-42s новое %3d  Re %3d  всего %3d" % (mb, сч["новое"], сч["Re"], sum(сч.values())))
