# -*- coding: utf-8 -*-
"""События за сегодня по кампаниям (тип x кампания) и последние события по
письмам Meyer в очереди; свежие файлы логов в C:\\sender\\logs с хвостом по
meyer. Только чтение."""
import glob
import io
import os
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сч = Counter()
for t, cid in c.execute("SELECT e.event_type, m.campaign_id FROM events e LEFT JOIN messages m ON m.id=e.message_id "
                        "WHERE e.event_ts>='2026-10-22'"):
    сч[(кам.get(cid, cid), t)] += 1
for k, v in sorted(сч.items(), key=lambda x: str(x)):
    print("  %4d  %s" % (v, k))
print("\nсообщения Meyer в очереди — последние события:")
for mid, cid, st, sa in c.execute("SELECT id, campaign_id, status, scheduled_at FROM messages WHERE campaign_id IN (13,14,18) "
                                  "AND status IN ('scheduled','sending') ORDER BY scheduled_at LIMIT 8"):
    е = c.execute("SELECT event_ts, event_type, substr(detail_json,1,160) FROM events WHERE message_id=? ORDER BY id DESC LIMIT 2", (mid,)).fetchall()
    print("  #%d к%s %s %s | %s" % (mid, cid, st, sa[:16], е))
for п in sorted(glob.glob(r"C:\sender\logs\*") + glob.glob(r"C:\sender\*.log"), key=os.path.getmtime)[-4:]:
    print("\n== %s (%d КБ)" % (п, os.path.getsize(п) // 1024))
    стр = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for s in [s for s in стр if "meyer" in s.lower() or "18" in s and "camp" in s.lower()][-8:]:
        print("   ", s[:220])
    for s in стр[-5:]:
        print("  хвост:", s[:220])
