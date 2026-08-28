# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM events WHERE id=301897").fetchone()
if r is None:
    print("события 301897 нет")
else:
    for к in r.keys():
        v = r[к]
        if к == "detail_json" and v:
            d = json.loads(v)
            print("detail:")
            for kk, vv in d.items():
                print("    %-16s %s" % (kk, str(vv)[:260]))
            continue
        print("%-14s %s" % (к, str(v)[:120]))
print("")
print("=== получатель и лид ===")
for x in c.execute("SELECT id, email, inn, company_name FROM recipients "
                   " WHERE email LIKE '%npk-kanzler.ru' OR domain='npk-kanzler.ru'"):
    print("   rid %s | %s | ИНН %s | %s" % (x["id"], x["email"], x["inn"],
                                            str(x["company_name"])[:34]))
    for l in c.execute("SELECT id, status, reply_kind, phone, need, created_at "
                       "  FROM leads WHERE recipient_id=?", (x["id"],)):
        print("      лид #%s %s | %s | %s" % (l["id"], l["status"], l["reply_kind"],
                                              str(l["need"] or "")[:90]))
    for e2 in c.execute("SELECT id, event_type, event_ts FROM events "
                        " WHERE recipient_id=? ORDER BY event_ts", (x["id"],)):
        print("      #%-7s %-11s %s" % (e2["id"], e2["event_type"],
                                        str(e2["event_ts"])[:16]))
print("")
print("=== последние лиды ===")
for l in c.execute("SELECT id, email, recipient_id, status, created_at FROM leads "
                   " ORDER BY id DESC LIMIT 5"):
    print("   #%-5s %-30s rid=%-7s %-14s %s" % (l["id"], str(l["email"])[:30],
                                                l["recipient_id"], l["status"],
                                                str(l["created_at"])[:16]))
c.close()
