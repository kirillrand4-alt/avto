# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timezone
АДРЕСА = ["isaev@findcon.ru", "aseitov@asiacement.ru", "a.udachin@sodrugestvo.ru",
          "postmaster@agrotek.com"]
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("сейчас UTC: %s" % datetime.now(timezone.utc).isoformat()[:19])
print("последнее событие в базе: %s"
      % c.execute("SELECT MAX(event_ts) FROM events").fetchone()[0])
print("")
for а in АДРЕСА:
    дом = а.split("@")[1]
    print("=== %s ===" % а)
    n = c.execute("SELECT COUNT(*) FROM events e "
                  "  WHERE COALESCE(e.detail_json,'') LIKE ?",
                  ("%" + а + "%",)).fetchone()[0]
    print("   событий с этим адресом в detail: %d" % n)
    for r in c.execute("SELECT id, email, inn, company_name FROM recipients "
                       " WHERE email=? OR domain=?", (а, дом)):
        print("   получатель: rid %s %-28s %s" % (r["id"], str(r["email"])[:28],
                                                  str(r["company_name"] or "")[:34]))
        for x in c.execute("SELECT id, event_type, event_ts FROM events "
                           " WHERE recipient_id=? ORDER BY event_ts DESC LIMIT 4",
                           (r["id"],)):
            print("      #%-7s %-11s %s" % (x["id"], x["event_type"],
                                            str(x["event_ts"])[:16]))
        for l in c.execute("SELECT id, status, reply_kind FROM leads "
                           " WHERE recipient_id=?", (r["id"],)):
            print("      лид #%s %s %s" % (l["id"], l["status"], l["reply_kind"]))
c.close()
