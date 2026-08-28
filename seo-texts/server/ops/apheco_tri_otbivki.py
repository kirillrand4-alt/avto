# -*- coding: utf-8 -*-
"""Три отбивки по comm_dep@apheco.ru — три письма или три уведомления?"""
import json
import sqlite3
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== письма на этот адрес ===")
for m in c.execute(
        "SELECT m.id, m.sent_at, m.status, m.mailbox_id, m.rfc_message_id "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE LOWER(r.email)='comm_dep@apheco.ru' ORDER BY m.id"):
    print("  msg=%s %s %s ящик=%s rfc=%s"
          % (m["id"], str(m["sent_at"])[:19], m["status"], m["mailbox_id"],
             str(m["rfc_message_id"])[:40]))
print("=== журнал отправок ===")
for s in c.execute("SELECT ts, outcome, rfc_message_id FROM send_log "
                   " WHERE LOWER(email)='comm_dep@apheco.ru' ORDER BY ts"):
    print("  %s %s %s" % (str(s["ts"])[:19], s["outcome"],
                          str(s["rfc_message_id"])[:40]))
print("=== события ===")
for e in c.execute(
        "SELECT e.id, e.event_ts, e.dedup_key, e.mailbox_id, e.detail_json "
        "  FROM events e JOIN recipients r ON r.id=e.recipient_id "
        " WHERE LOWER(r.email)='comm_dep@apheco.ru' ORDER BY e.event_ts"):
    d = {}
    try:
        d = json.loads(e["detail_json"] or "{}")
    except Exception:
        pass
    dsn = d.get("dsn") if isinstance(d.get("dsn"), dict) else {}
    print("  ev=%s %s ключ=%s" % (e["id"], str(e["event_ts"])[:19],
                                  str(e["dedup_key"])[:36]))
    print("     вердикт=%s :: %s" % (dsn.get("verdict") or "—",
                                     " ".join(str(d.get("snippet") or "")
                                              .split())[:200]))
c.close()
