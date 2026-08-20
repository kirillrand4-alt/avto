# -*- coding: utf-8 -*-
"""Последние карточки очереди: кто, когда, каким письмом."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for r in c.execute(
        "SELECT cr.id rid, cr.status, cr.email, cr.message_id mid, "
        "       cr.created_at, r.company_name, r.inn "
        "FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
        "ORDER BY cr.id DESC LIMIT 6"):
    print(f"  #{r['rid']} письмо {r['mid']} {r['status']:<9} "
          f"{str(r['company_name'])[:32]:<32} {r['email']} "
          f"{str(r['created_at'])[:19]}")
print()
for r in c.execute("SELECT id, campaign_id, recipient_id, status, created_at "
                   "FROM messages WHERE id=2805"):
    print(f"  письмо 2805: кампания {r['campaign_id']} получатель "
          f"{r['recipient_id']} {r['status']} {str(r['created_at'])[:19]}")
