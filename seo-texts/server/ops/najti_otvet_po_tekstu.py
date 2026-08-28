# -*- coding: utf-8 -*-
import json, sqlite3, sys
КУСОК = sys.argv[1] if len(sys.argv) > 1 else "очень актуальная"
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("ищу: %r" % КУСОК)
print("")
print("=== в событиях ===")
for r in c.execute("SELECT id, event_type, event_ts, recipient_id, mailbox_id, "
                   "       detail_json FROM events "
                   " WHERE detail_json LIKE ? ORDER BY event_ts DESC LIMIT 6",
                   ("%" + КУСОК + "%",)):
    d = json.loads(r["detail_json"] or "{}")
    h = d.get("headers") or {}
    print("   #%-7s %-11s %s rid=%s ящик %s"
          % (r["id"], r["event_type"], str(r["event_ts"])[:16], r["recipient_id"],
             str(r["mailbox_id"])[:30]))
    print("      От: %s" % str(h.get("From") or "")[:70])
    print("      Тема: %s" % str(h.get("Subject") or "")[:70])
    print("      Текст: %s" % str(d.get("snippet") or "").replace("\n", " ")[:220])
print("")
print("=== в лидах ===")
for r in c.execute("SELECT id, status, reply_kind, email, company_name, phone, "
                   "       need, created_at FROM leads WHERE need LIKE ? "
                   " ORDER BY id DESC LIMIT 5", ("%" + КУСОК + "%",)):
    print("   лид #%-4s %-14s %-12s %-26s %s"
          % (r["id"], r["status"], r["reply_kind"], str(r["email"])[:26],
             str(r["created_at"])[:16]))
    print("      %s | тел %s" % (str(r["company_name"] or "")[:40], r["phone"]))
    print("      %s" % str(r["need"] or "").replace("\n", " ")[:200])
c.close()
