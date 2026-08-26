# -*- coding: utf-8 -*-
"""Куда делся ответ «Шато де Талю»: письмо, события, карточка лида."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

print("=== получатели домена chateaudetalu.ru ===")
recs = c.execute("SELECT id, inn, email, company_name FROM recipients "
                 " WHERE email LIKE '%chateaudetalu%' OR domain LIKE '%chateaudetalu%'"
                 ).fetchall()
for r in recs:
    print("   #%s %s | %s | ИНН %s" % (r["id"], r["email"],
                                       str(r["company_name"])[:40], r["inn"]))

ids = [r["id"] for r in recs]
if ids:
    зн = ",".join("?" * len(ids))
    print("")
    print("=== письма ===")
    for m in c.execute(
            "SELECT cr.id crid, cr.status, cr.message_id, cr.created_at, "
            "       m.status mst, m.sent_at, substr(cr.subject,1,50) s "
            "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
            " WHERE cr.recipient_id IN (%s) ORDER BY cr.id" % зн, ids):
        print("   карточка #%-6s %-9s письмо %-12s ушло %s | %s"
              % (m["crid"], m["status"], m["mst"] or "—",
                 str(m["sent_at"])[:19] if m["sent_at"] else "—", m["s"]))
    print("")
    print("=== события ===")
    for e in c.execute(
            "SELECT id, event_type, event_ts, message_id, detail_json "
            "  FROM events WHERE recipient_id IN (%s) ORDER BY event_ts" % зн, ids):
        d = json.loads(e["detail_json"] or "{}")
        сн = " ".join(str(d.get("snippet") or "").split())[:70]
        print("   %-16s %s письмо=%s %s"
              % (e["event_type"], str(e["event_ts"])[:19],
                 e["message_id"] or "—", сн))
    print("")
    print("=== карточки лидов ===")
    for l in c.execute(
            "SELECT id, email, reply_kind, status, thread_id, created_at, "
            "       substr(need,1,110) n FROM leads "
            " WHERE recipient_id IN (%s) OR email LIKE '%%chateaudetalu%%'" % зн,
            ids):
        print("   лид #%s %s | %s | %s | ветка %s"
              % (l["id"], l["email"], l["reply_kind"], l["status"],
                 (l["thread_id"] or "нет")[:40]))
        print("      %s" % str(l["n"]).replace("\n", " ")[:110])

print("")
print("=== все события с упоминанием домена в snippet/from ===")
for e in c.execute("SELECT id, event_type, event_ts, recipient_id, detail_json "
                   "  FROM events WHERE detail_json LIKE '%chateaudetalu%' "
                   " ORDER BY event_ts"):
    d = json.loads(e["detail_json"] or "{}")
    print("   %-16s %s пол=%s %s" % (e["event_type"], str(e["event_ts"])[:19],
                                     e["recipient_id"],
                                     " ".join(str(d.get("snippet") or "").split())[:60]))
c.close()
