# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT id, email, inn, company_name FROM recipients "
              " WHERE email='info@chocolada.ru'").fetchone()
print("получатель: rid %s | %s | ИНН %s" % (r["id"], r["email"], r["inn"]))
l = c.execute("SELECT * FROM leads WHERE recipient_id=? OR email=?",
              (r["id"], r["email"])).fetchone()
if l:
    print("")
    print("=== карточка лида ===")
    for к in ("id", "status", "reply_kind", "phone", "need", "readiness",
              "thread_id", "created_at"):
        if к in l.keys():
            print("   %-12s %r" % (к, l[к]))
print("")
print("=== события ===")
for x in c.execute("SELECT id, event_type, event_ts, detail_json FROM events "
                   " WHERE recipient_id=? ORDER BY event_ts", (r["id"],)):
    print("   #%-7s %-11s %s" % (x["id"], x["event_type"], str(x["event_ts"])[:19]))
    if x["event_type"] in ("reply", "reply_auto", "other"):
        d = json.loads(x["detail_json"] or "{}")
        print("      kind=%s | привязка=%s" % (d.get("kind"), d.get("privyazka")))
        print("      ТЕКСТ: %s" % str(d.get("snippet") or "(пусто)")[:900])
c.close()
