# -*- coding: utf-8 -*-
"""Входящее целиком по адресу: нужно имя и контекст."""
import sqlite3
import sys

а = sys.argv[1].lower()
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for r in c.execute(
        "SELECT id, company_name, inn, COALESCE(need,'') need FROM leads "
        "WHERE lower(COALESCE(email,''))=? OR lower(COALESCE(need,'')) LIKE ? "
        "ORDER BY id DESC LIMIT 1", (а, f"%{а}%")):
    print(f"лид #{r['id']} {r['company_name']} ИНН {r['inn']}")
    print(str(r["need"])[:2000])
print("\n== карточка очереди ==")
for r in c.execute(
        "SELECT cr.id, cr.status, cr.email, cr.subject, COALESCE(cr.reason,'') rs, "
        "       cr.message_id, cr.campaign_id, cr.recipient_id, "
        "       substr(COALESCE(cr.body,''),1,300) начало "
        "FROM confirm_reviews cr WHERE lower(cr.email)=?", (а,)):
    print(dict(r))
