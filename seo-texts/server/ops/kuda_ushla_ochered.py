# -*- coding: utf-8 -*-
"""Куда ушли письма из очереди за последние N часов: статус × кампания × причина. Только чтение."""
import sqlite3, sys
from collections import Counter
from datetime import datetime, timedelta
ч = float(sys.argv[1]) if len(sys.argv) > 1 else 3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кол = [r[1] for r in c.execute("PRAGMA table_info(messages)")]
print("колонки:", кол)
пр = next((k for k in ("skip_reason", "last_error", "error", "reason") if k in кол), None)
от = (datetime.utcnow() - timedelta(hours=ч)).strftime("%Y-%m-%dT%H:%M:%S")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сч = Counter()
for st, ки, p in c.execute("SELECT status, campaign_id, %s FROM messages WHERE updated_at >= ?" % (пр or "''"), (от,)):
    сч[(st, кам.get(ки, ки), str(p or "")[:90])] += 1
for k, v in сч.most_common(40): print("%5d  %s | %s | %s" % ((v,) + k))
print("--- сейчас в очереди по статусам:")
for r in c.execute("SELECT status, COUNT(*) FROM messages WHERE status IN ('pending_review','approved','scheduled','sending') GROUP BY status"): print(r)
