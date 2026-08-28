# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM events WHERE id=305587").fetchone()
d = json.loads(r["detail_json"] or "{}")
print("event_type=%s | recipient_id=%s" % (r["event_type"], r["recipient_id"]))
for к in ("kind", "privyazka", "reply_kind", "in_reply_to_hdr"):
    print("   %-16s %r" % (к, d.get(к)))
h = d.get("headers") or {}
print("   Subject: %s" % str(h.get("Subject") or "")[:80])
print("   In-Reply-To: %s" % str(h.get("In-Reply-To") or "—")[:60])
print("   References: %s" % str(h.get("References") or "—")[:60])
print("")
rec = c.execute("SELECT id, email, inn, company_name FROM recipients WHERE id=29417").fetchone()
print("получатель: %s | %s | ИНН %s" % (rec["email"], rec["company_name"], rec["inn"]))
л = c.execute("SELECT id, status FROM leads WHERE recipient_id=29417").fetchone()
print("лид: %s" % (dict(л) if л else "НЕТ"))
print("")
print("=== все события этого получателя ===")
for x in c.execute("SELECT id, event_type, event_ts FROM events "
                   " WHERE recipient_id=29417 ORDER BY event_ts"):
    print("   #%-7s %-11s %s" % (x["id"], x["event_type"], str(x["event_ts"])[:16]))
c.close()
