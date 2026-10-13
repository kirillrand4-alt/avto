# -*- coding: utf-8 -*-
"""Все лиды компании по подстроке имени/почты: статус, Bitrix, даты."""
import sqlite3
import sys
м = sys.argv[1].lower()
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for л in c.execute("SELECT id, company_name, email, inn, status, reply_kind, bitrix_lead_id, "
                   "created_at, updated_at FROM leads ORDER BY id"):
    if м in str(л["company_name"] or "").lower() or м in str(л["email"] or "").lower():
        print("#%s %s <%s> ИНН %s | %s | %s | bitrix=%s | создан %s, изм. %s" % (
            л["id"], л["company_name"], л["email"], л["inn"], л["status"], л["reply_kind"],
            л["bitrix_lead_id"], str(л["created_at"])[:16], str(л["updated_at"])[:16]))
print("=== ЛИДЫ КОМПАНИИ ===")
