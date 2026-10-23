# -*- coding: utf-8 -*-
"""Письма на адрес (или домен): pisma_na_adres.py <адрес|@домен>. Только чтение."""
import sqlite3
import sys
к = sys.argv[1].lower()
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
усл = "lower(r.email) LIKE ?" if к.startswith("@") else "lower(r.email) = ?"
for r in c.execute("SELECT m.id, m.status, m.sent_at, m.mailbox_id, k.name, r.email, r.inn, r.company_name, m.subject "
                   "FROM messages m JOIN recipients r ON r.id=m.recipient_id JOIN campaigns k ON k.id=m.campaign_id "
                   "WHERE " + усл + " ORDER BY m.id", ("%" + к if к.startswith("@") else к,)):
    print(r)
