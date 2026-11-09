# -*- coding: utf-8 -*-
"""Получатели по подстроке названия компании + последние отправки им: poluchatel_po_nazvaniyu.py ПОДСТРОКА. Только чтение."""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
for rid, em, имя, inn in c.execute("SELECT id, email, company_name, inn FROM recipients WHERE company_name LIKE ? LIMIT 20", ("%" + sys.argv[1] + "%",)):
    п = c.execute("SELECT mailbox_id, status, substr(sent_at,1,16) FROM messages WHERE recipient_id=? ORDER BY id DESC LIMIT 1", (rid,)).fetchone()
    print(rid, em, имя, inn, п)
