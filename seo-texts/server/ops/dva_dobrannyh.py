# -*- coding: utf-8 -*-
"""Доехали ли до базы ответы «ПК Контур» и «Промкомплектация»."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
for адрес in ("maklygin-ka@pk-kontur.ru", "zakaz@pk16.ru"):
    print("")
    print("=== %s ===" % адрес)
    дом = адрес.rsplit("@", 1)[-1]
    recs = c.execute("SELECT id, email, company_name FROM recipients "
                     " WHERE email=? OR lower(domain)=? OR lower(email) LIKE ?",
                     (адрес, дом, "%@" + дом)).fetchall()
    for r in recs:
        print("   получатель #%s %s (%s)" % (r["id"], r["email"],
                                             str(r["company_name"])[:40]))
    ids = [r["id"] for r in recs]
    if ids:
        зн = ",".join("?" * len(ids))
        for e in c.execute("SELECT id, event_type, event_ts, detail_json "
                           "  FROM events WHERE recipient_id IN (%s) "
                           " ORDER BY event_ts DESC LIMIT 4" % зн, ids):
            d = json.loads(e["detail_json"] or "{}")
            print("   событие #%s %s %s | %s"
                  % (e["id"], e["event_type"], str(e["event_ts"])[:16],
                     " ".join(str(d.get("snippet") or "").split())[:80]))
        for l in c.execute("SELECT id, email, reply_kind, status, created_at, "
                           "       substr(need,1,120) n FROM leads "
                           " WHERE recipient_id IN (%s)" % зн, ids):
            print("   ЛИД #%s %s | %s | %s" % (l["id"], l["email"],
                                               l["reply_kind"], l["status"]))
            print("      %s" % str(l["n"]).replace("\n", " ")[:120])
    ищем = c.execute("SELECT id, event_type, event_ts, detail_json FROM events "
                     " WHERE detail_json LIKE ? ORDER BY id DESC LIMIT 3",
                     ("%" + адрес + "%",)).fetchall()
    for e in ищем:
        print("   по адресу в detail: #%s %s %s"
              % (e["id"], e["event_type"], str(e["event_ts"])[:16]))
c.close()
