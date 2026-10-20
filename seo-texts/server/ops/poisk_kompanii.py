# -*- coding: utf-8 -*-
"""Найти компанию в базах по куску названия/домена: poisk_kompanii.py <кусок>...
Панель (recipients + письма), обогащение (companies), база обзвона."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
for к in sys.argv[1:]:
    л = "%" + к + "%"
    print("==== «%s»" % к)
    for r in c.execute("SELECT id, email, inn, company_name, segment FROM recipients WHERE company_name LIKE ? OR email LIKE ? LIMIT 12", (л, л)):
        писем = c.execute("SELECT group_concat(status) FROM messages WHERE recipient_id=?", (r[0],)).fetchone()[0]
        print("  панель:", r[1:], "| письма:", писем)
    кол = {x[1] for x in e.execute("PRAGMA table_info(companies)")}
    поля = ", ".join(x for x in ("inn", "name", "site", "region", "revenue_rub") if x in кол)
    for r in e.execute("SELECT %s FROM companies WHERE name LIKE ? OR site LIKE ? LIMIT 8" % поля, (л, л)):
        print("  обогащение:", r)
    for r in e.execute("SELECT inn, email FROM emails WHERE email LIKE ? LIMIT 5", (л,)):
        print("  адрес в обогащении:", r)
