# -*- coding: utf-8 -*-
"""Поиск по куску: получатели панели (имя/почта), лиды (имя/почта/need). Только чтение.
    nayti_kompaniyu.py <кусок> [<кусок2> ...]"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.create_function("lo", 1, lambda s: (s or "").lower())
for к in sys.argv[1:]:
    к = "%" + к.lower() + "%"
    print("==== ", к)
    for r in c.execute("SELECT id, inn, company_name, email FROM recipients WHERE lo(company_name) LIKE ? OR lo(email) LIKE ? LIMIT 15", (к, к)):
        print("  получатель", r)
    for r in c.execute("SELECT id, inn, company_name, email, status, reply_kind, substr(created_at,1,16), substr(need,1,120) FROM leads "
                       "WHERE lo(company_name) LIKE ? OR lo(email) LIKE ? OR lo(need) LIKE ? ORDER BY id DESC LIMIT 10", (к, к, к)):
        print("  лид", r)
