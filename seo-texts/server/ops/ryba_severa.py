# -*- coding: utf-8 -*-
"""Где ответ «Рыбы Севера»: событие есть, а карточки лида нет?"""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
rec = c.execute("SELECT id, inn, email, company_name FROM recipients "
                " WHERE email='r.krutov@pk-flipper.ru' OR inn='5017140044'"
                ).fetchall()
for r in rec:
    print("получатель #%s %s (%s) ИНН %s"
          % (r["id"], r["email"], str(r["company_name"])[:40], r["inn"]))
ids = [r["id"] for r in rec]
if not ids:
    raise SystemExit(0)
зн = ",".join("?" * len(ids))
print("")
print("=== события ===")
for e in c.execute("SELECT id, event_type, event_ts, mailbox_id, detail_json "
                   "  FROM events WHERE recipient_id IN (%s) "
                   " ORDER BY event_ts" % зн, ids):
    d = json.loads(e["detail_json"] or "{}")
    print("   #%-7s %-12s %s %s"
          % (e["id"], e["event_type"], str(e["event_ts"])[:19],
             " ".join(str(d.get("snippet") or "").split())[:90]))
print("")
print("=== карточки лидов ===")
л = c.execute("SELECT id, email, reply_kind, status, created_at, "
              "       substr(need,1,120) n FROM leads "
              " WHERE recipient_id IN (%s)" % зн, ids).fetchall()
if not л:
    print("   НЕТ НИ ОДНОЙ")
for x in л:
    print("   #%s %s | %s | %s" % (x["id"], x["email"], x["reply_kind"], x["status"]))
    print("      %s" % str(x["n"]).replace("\n", " ")[:110])
print("")
print("=== письма ===")
for m in c.execute("SELECT id, status, sent_at, mailbox_id, has_reply "
                   "  FROM messages WHERE recipient_id IN (%s) "
                   " ORDER BY id DESC LIMIT 4" % зн, ids):
    print("   #%s %s %s %s has_reply=%s" % (m["id"], m["status"],
                                            str(m["sent_at"])[:19],
                                            m["mailbox_id"], m["has_reply"]))
c.close()
