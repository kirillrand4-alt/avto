# -*- coding: utf-8 -*-
"""Что за кампании 7-9 и куда встали их одобренные письма."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("кампании:")
for r in c.execute("SELECT id, name FROM campaigns WHERE id IN (7,8,9,10,11)"):
    print(f"  {r['id']}  {r['name']}")
print("\nодобренные письма старых кампаний:")
for r in c.execute(
        "SELECT m.campaign_id k, m.status s, substr(m.scheduled_at,1,10) d, "
        "COUNT(*) n FROM messages m JOIN confirm_reviews r ON r.message_id=m.id "
        "WHERE m.campaign_id NOT IN (10,11) AND r.status IN ('approved','edited') "
        "GROUP BY m.campaign_id, m.status, d ORDER BY d DESC LIMIT 12"):
    print(f"  кампания {r['k']}  {r['s']:<12} {r['d']}  {r['n']}")
