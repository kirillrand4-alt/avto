# -*- coding: utf-8 -*-
"""Ответы людей получателям кампании (по умолч. 17 «КЦ-1 август»): на какое
письмо пришёл ответ — ящик ответа, время, все письма этому получателю."""
import json
import sqlite3
import sys
КАМП = int(sys.argv[1]) if len(sys.argv) > 1 else 17
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
кол = [r[1] for r in c.execute("PRAGMA table_info(events)")]
print("колонки events:", кол)
rids = {r[0] for r in c.execute("SELECT recipient_id FROM messages WHERE status='sent' AND campaign_id=?", (КАМП,))}
for row in c.execute("SELECT * FROM events WHERE event_type='reply' ORDER BY event_ts"):
    z = dict(zip(кол, row))
    if z.get("recipient_id") not in rids:
        continue
    d = json.loads(z.get("detail_json") or "{}")
    print("\n== ответ", z.get("event_ts"), "ящик", z.get("mailbox_id"), "msg", z.get("message_id"),
          "| тема:", str(d.get("subject") or "")[:80], "| от:", str(d.get("from") or "")[:50])
    for m in c.execute("SELECT id, campaign_id, mailbox_id, sent_at, subject FROM messages WHERE recipient_id=? AND status='sent' ORDER BY sent_at",
                       (z["recipient_id"],)):
        print("   письмо", m[0], кам.get(m[1]), m[2], str(m[3])[:16], "|", str(m[4])[:60])
