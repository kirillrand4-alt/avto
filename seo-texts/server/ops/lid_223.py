# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM leads WHERE id=223").fetchone()
if r:
    for к in r.keys():
        v = str(r[к] or "")
        if v:
            print("   %-18s %s" % (к, v[:150]))
print("")
print("=== последние 5 лидов ===")
for x in c.execute("SELECT id, email, recipient_id, status, reply_kind, created_at "
                   "  FROM leads ORDER BY id DESC LIMIT 5"):
    print("   #%-5s %-30s rid=%-7s %-10s %s"
          % (x["id"], str(x["email"])[:30], x["recipient_id"], x["status"],
             str(x["created_at"])[:16]))
c.close()
