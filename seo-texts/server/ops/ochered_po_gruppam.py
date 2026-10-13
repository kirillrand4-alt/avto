# -*- coding: utf-8 -*-
"""Очередь подтверждения: сколько писем по кампаниям и группам (только чтение)."""
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
св = Counter()
for cid, ex, n in c.execute("SELECT m.campaign_id, r.extra_json, count(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                            "WHERE m.status='pending_review' GROUP BY m.campaign_id, r.extra_json"):
    гр = "Россия 9000" if "Россия 9000" in str(ex) else ("Белорусь 1000" if "Белорусь 1000" in str(ex) else "без группы 9000/1000")
    св[(cid, гр)] += n
for (cid, гр), n in sorted(св.items()):
    print("кампания %s | %s: %d" % (cid, гр, n))
print("кампании:", c.execute("SELECT id, name FROM campaigns WHERE id IN (%s)" % ",".join(str(k[0]) for k in св) ).fetchall() if св else "")
print("=== ОЧЕРЕДЬ ПО ГРУППАМ ===")
