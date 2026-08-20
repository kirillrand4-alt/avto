# -*- coding: utf-8 -*-
"""Сколько писем прямо сейчас ждёт отправки и сколько уже ушло сегодня."""
import sqlite3
from datetime import datetime, timezone

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
сегодня = datetime.now(timezone.utc).date().isoformat()

print("== одобренные письма, ждут слота ==")
всего = 0
for r in c.execute(
        "SELECT m.campaign_id k, m.status s, COUNT(*) n FROM messages m "
        "JOIN confirm_reviews r ON r.message_id=m.id "
        "WHERE r.status IN ('approved','edited') "
        "AND m.status IN ('scheduled','sending') "
        "GROUP BY m.campaign_id, m.status ORDER BY m.campaign_id"):
    print(f"  кампания {r['k']:<3} {r['s']:<10} {r['n']}")
    всего += r["n"]
print(f"  ИТОГО ждут отправки: {всего}")

print("\n== ушло сегодня ==")
for r in c.execute(
        "SELECT campaign_id k, COUNT(*) n FROM messages "
        "WHERE status='sent' AND substr(updated_at,1,10)=? "
        "GROUP BY campaign_id", (сегодня,)):
    print(f"  кампания {r['k']:<3} {r['n']}")

print("\n== очередь подтверждения (pending) ==")
for r in c.execute("SELECT campaign_id k, COUNT(*) n FROM confirm_reviews "
                   "WHERE status='pending' GROUP BY campaign_id"):
    print(f"  кампания {r['k']:<3} {r['n']}")
