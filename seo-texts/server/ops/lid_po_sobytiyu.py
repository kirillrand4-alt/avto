# -*- coding: utf-8 -*-
"""Есть ли лид по событию ответа: lid_po_sobytiyu.py <event_id>"""
import json
import sqlite3
import sys

eid = int(sys.argv[1])
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
е = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
д = json.loads(е["detail_json"] or "{}")
print("событие:", е["event_type"], е["event_ts"], "получатель", е["recipient_id"], "| kind:", д.get("kind"),
      "| reply_kind:", д.get("reply_kind"), "| от:", (д.get("headers") or {}).get("From"))
р = c.execute("SELECT id, inn, email, company_name, extra_json FROM recipients WHERE id=?", (е["recipient_id"],)).fetchone()
print("получатель:", dict(р) if р else None)
for л in c.execute("SELECT id, email, inn, status, reply_kind, source_event_id, created_at, dedup_key FROM leads "
                   "WHERE source_event_id=? OR (inn=? AND inn<>'') OR recipient_id=? ORDER BY id DESC LIMIT 5",
                   (eid, р["inn"] if р else "", е["recipient_id"])):
    print("лид:", dict(л))
print("ключи detail:", sorted(д.keys()))
print("сниппет:", str(д.get("snippet") or "")[:300])
print("=== ЛИД ПО СОБЫТИЮ ===")
