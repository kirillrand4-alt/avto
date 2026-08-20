# -*- coding: utf-8 -*-
"""Та ли это «ВОЗДУХ», которую я снял из очереди как не-покупателя."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for r in c.execute(
        "SELECT cr.id rid, cr.status, cr.email, cr.message_id, cr.created_at, "
        "       r.inn, r.company_name "
        "FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
        "WHERE r.company_name LIKE '%ВОЗДУХ%' ORDER BY cr.id"):
    print(f"  карточка #{r['rid']} | письмо {r['message_id']} | "
          f"{r['status']:<9} | {r['email']} | ИНН {r['inn']} | "
          f"{r['company_name']} | {str(r['created_at'])[:19]}")
