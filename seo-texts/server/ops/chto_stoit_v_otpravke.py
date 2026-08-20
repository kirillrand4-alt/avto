# -*- coding: utf-8 -*-
"""Что реально стоит в отправке: по дате слота и состоянию письма."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("== письма по состоянию ==")
for s, n in c.execute("SELECT status, COUNT(*) n FROM messages "
                      "GROUP BY status ORDER BY n DESC"):
    print(f"  {s:<16} {n}")

print()
print("== одобренные карточки: где их письма ==")
ряды = c.execute(
    "SELECT m.status s, substr(m.scheduled_at,1,10) d, COUNT(*) n "
    "FROM confirm_reviews r JOIN messages m ON m.id = r.message_id "
    "WHERE r.status IN ('approved','edited') "
    "GROUP BY m.status, substr(m.scheduled_at,1,10) "
    "ORDER BY d, m.status").fetchall()
for r in ряды:
    print(f"  {str(r['d']):<12} {r['s']:<16} {r['n']}")

print()
print("== отправлено по дням (последние 7) ==")
for d, n in c.execute(
        "SELECT substr(sent_at,1,10) d, COUNT(*) n FROM send_log "
        "GROUP BY d ORDER BY d DESC LIMIT 7"):
    print(f"  {d}  {n}")
