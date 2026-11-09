# -*- coding: utf-8 -*-
"""Лиды и события reply по подстроке адреса/домена: lidy_po_domenu.py ПОДСТРОКА [...]. Только чтение."""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
шк = [x[1] for x in c.execute("PRAGMA table_info(leads)")]
for п in sys.argv[1:]:
    print("==", п)
    for r in c.execute("SELECT * FROM leads WHERE lower(%s) LIKE ?" % ("email" if "email" in шк else шк[1]), ("%" + п.lower() + "%",)):
        д = dict(zip(шк, r)); print("  ЛИД", {k: str(д[k])[:60] for k in шк if k in ("id", "email", "status", "created_at", "reply_kind", "owner", "assigned_to", "company_name", "inn", "stage")})
    for r in c.execute("SELECT r.email, cr.status, cr.kind, substr(cr.created_at,1,16), cr.subject FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id WHERE lower(r.email) LIKE ? ORDER BY cr.id DESC LIMIT 6", ("%" + п.lower() + "%",)):
        print("  КАРТ", r)
