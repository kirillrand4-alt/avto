# -*- coding: utf-8 -*-
"""Всё, что знаем о компании по ИНН: база обзвона, обогащение (адреса, люди,
телефоны, проба), наши письма/лиды. Только чтение.  kontakty_inn.py <ИНН>"""
import sqlite3
import sys
инн = sys.argv[1]
o = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro", uri=True, timeout=60)
o.row_factory = sqlite3.Row
r = o.execute("SELECT * FROM obzvon WHERE inn=?", (инн,)).fetchone()
if r:
    for k in ("division", "name_short", "region", "address", "okved_main", "revenue", "ssch", "director", "phones_base", "emails_base",
              "sites", "phones_site", "emails_site", "equip_by_okved"):
        if k in r.keys() and r[k]:
            print("обзвон.%s: %s" % (k, str(r[k])[:300]))
else:
    print("в базе обзвона нет")
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
for t in ("emails", "phone_contacts"):
    cols = [x[1] for x in e.execute("PRAGMA table_info(%s)" % t)]
    for row in e.execute("SELECT * FROM %s WHERE inn=?" % t, (инн,)):
        print("обогащение.%s:" % t, {k: v for k, v in zip(cols, row) if v not in (None, "") and k not in ("inn", "updated_at")})
try:
    cols = [x[1] for x in e.execute("PRAGMA table_info(companies)")]
    for row in e.execute("SELECT * FROM companies WHERE inn=?", (инн,)):
        print("обогащение.companies:", {k: str(v)[:200] for k, v in zip(cols, row) if v not in (None, "")})
except sqlite3.Error:
    pass
s = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in s.execute("SELECT id, name FROM campaigns")}
проба = {r[0].lower(): r[1] for r in s.execute("SELECT email, verdict FROM addr_probe")}
for row in s.execute("SELECT r.email, m.status, m.campaign_id, substr(coalesce(m.sent_at,''),1,10), m.subject FROM recipients r "
                     "LEFT JOIN messages m ON m.recipient_id=r.id WHERE r.inn=?", (инн,)):
    print("панель:", row[0], "| проба:", проба.get((row[0] or "").lower()), "|", row[1], кам.get(row[2]), row[3], "|", (row[4] or "")[:60])
for row in s.execute("SELECT id, status, reply_kind, email, substr(need,1,150) FROM leads WHERE inn=?", (инн,)):
    print("лид:", row)
