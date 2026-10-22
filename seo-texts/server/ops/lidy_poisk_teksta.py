# -*- coding: utf-8 -*-
"""Лиды, в тексте ответа которых есть подстрока (за N дней). Только чтение.
    lidy_poisk_teksta.py <подстрока> [дней=3]"""
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
д = int(sys.argv[2]) if len(sys.argv) > 2 else 3
for r in c.execute("SELECT id, email, company_name, inn, status, reply_kind, phone, created_at, updated_at, need FROM leads "
                   "WHERE updated_at>=strftime('%Y-%m-%dT%H:%M:%S','now',?) AND need LIKE ? ORDER BY updated_at DESC",
                   ("-%d days" % д, "%" + sys.argv[1] + "%")):
    print("=" * 60)
    print("лид %s | %s | %s | ИНН %s | %s/%s | тел %s | создан %s | обновлён %s" % r[:9])
    print(str(r[9])[:2500])
