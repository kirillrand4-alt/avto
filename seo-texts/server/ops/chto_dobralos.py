# -*- coding: utf-8 -*-
"""Что появилось в базе после добора ящиков."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
print("=== события за последний час ===")
for r in c.execute(
        "SELECT id, event_type, event_ts, recipient_id, detail_json FROM events "
        " WHERE created_at >= datetime('now','-1 hour') "
        "    OR id > (SELECT MAX(id)-40 FROM events) ORDER BY id DESC LIMIT 25"):
    d = json.loads(r["detail_json"] or "{}")
    т = " ".join(str(d.get("snippet") or "").split())[:80]
    print("   #%-7s %-11s %s пол=%-6s %s"
          % (r["id"], r["event_type"], str(r["event_ts"])[:16],
             r["recipient_id"], т))
print("")
print("=== свежие карточки лидов ===")
for r in c.execute(
        "SELECT id, email, reply_kind, status, created_at, recipient_id, "
        "       substr(need,1,80) n FROM leads ORDER BY id DESC LIMIT 12"):
    print("   #%-5s %-34s %-14s пол=%-6s %s"
          % (r["id"], str(r["email"])[:34], r["reply_kind"], r["recipient_id"],
             str(r["created_at"])[:16]))
    print("      %s" % str(r["n"]).replace("\n", " ")[:80])
c.close()
