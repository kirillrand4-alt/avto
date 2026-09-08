# -*- coding: utf-8 -*-
"""Только чтение: почему письмо 6929 не видно в переписке компании."""
import io
import re
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for р in c.execute(
        "SELECT m.id, m.recipient_id, m.status, m.sent_at, m.mailbox_id,"
        " m.subject, r.email, r.inn, r.company_name, LENGTH(IFNULL("
        "m.body_rendered,'')) тело FROM messages m JOIN recipients r"
        " ON r.id=m.recipient_id WHERE m.id IN (6929, 11805)"):
    print("  msg=%s rid=%s inn=%s %s | %s | тело=%d байт | %s"
          % (р["id"], р["recipient_id"], р["inn"], р["status"],
             р["email"], р["тело"], str(р["subject"])[:40]))
c.close()

т = io.open(r"C:\sender\sender\store.py", encoding="utf-8",
            errors="ignore").read()
i = т.find("def dialog_thread_company")
print("\n=== dialog_thread_company: как выбирает письма ===")
print(т[i:i + 1800])
