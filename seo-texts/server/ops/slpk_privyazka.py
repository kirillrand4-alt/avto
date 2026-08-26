# -*- coding: utf-8 -*-
"""Привяжется ли ответ с zakupka@slpk.com к карточке СЛПК."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
ряды = c.execute("SELECT id, inn, email, company_name FROM recipients "
                 " WHERE lower(domain)='slpk.com' OR lower(email) LIKE '%@slpk.com'"
                 ).fetchall()
print("получателей на домене slpk.com: %d" % len(ряды))
for r in ряды:
    print("   #%s %-28s ИНН %-14s %s" % (r["id"], r["email"], r["inn"],
                                         str(r["company_name"])[:40]))
инны = {str(r["inn"] or "") for r in ряды}
инны.discard("")
print("")
print("разных ИНН на домене: %d → привязка по домену %s"
      % (len(инны), "сработает" if len(инны) <= 1 and ряды else "НЕ сработает"))
c.close()
