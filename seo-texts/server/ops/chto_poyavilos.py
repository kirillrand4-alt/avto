# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== новые события ===")
for r in c.execute("SELECT id, event_type, event_ts, recipient_id, detail_json "
                   "  FROM events ORDER BY id DESC LIMIT 4"):
    d = json.loads(r["detail_json"] or "{}")
    h = d.get("headers") or {}
    print("   #%-7s %-11s %s rid=%s от %s"
          % (r["id"], r["event_type"], str(r["event_ts"])[:16], r["recipient_id"],
             str(h.get("From") or "")[:40]))
    т = str(d.get("snippet") or "").replace("\n", " ")
    if т.strip():
        print("      %s" % т[:200])
print("")
print("=== лиды по этим компаниям ===")
for rid in (29672, 30100, 16700):
    r = c.execute("SELECT email, company_name FROM recipients WHERE id=?",
                  (rid,)).fetchone()
    l = c.execute("SELECT id, status, reply_kind, phone, created_at FROM leads "
                  " WHERE recipient_id=?", (rid,)).fetchone()
    print("   rid %-6s %-28s %-30s -> %s"
          % (rid, str(r["email"])[:28], str(r["company_name"] or "")[:30],
             ("лид #%s %s %s тел %s" % (l["id"], l["status"], l["reply_kind"],
                                        l["phone"])) if l else "лида нет"))
c.close()
