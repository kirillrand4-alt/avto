# -*- coding: utf-8 -*-
"""Найти ответ/лид по куску названия или адреса: lid_poisk.py <строка>. Только чтение."""
import sqlite3, sys
q = "%" + sys.argv[1] + "%"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
print("лиды:", c.execute("SELECT id, status, reply_kind, email, company_name, created_at, updated_at FROM leads WHERE company_name LIKE ? OR email LIKE ?", (q, q)).fetchall())
rid = [r[0] for r in c.execute("SELECT id FROM recipients WHERE company_name LIKE ? OR email LIKE ?", (q, q))]
print("получатели:", rid[:10])
for r in rid[:10]:
    for e in c.execute("SELECT event_type, event_ts, substr(detail_json,1,200) FROM events WHERE recipient_id=? ORDER BY id DESC LIMIT 6", (r,)): print("  ", r, e)
print("входящие без получателя (по detail):", c.execute("SELECT event_type, event_ts, substr(detail_json,1,250) FROM events WHERE detail_json LIKE ? ORDER BY id DESC LIMIT 5", (q,)).fetchall())
