# -*- coding: utf-8 -*-
"""Message-ID и тема входящего письма по id события (для ответа в ветку).
    otvet_msgid.py <event_id>"""
import json
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
dj, rid = c.execute("SELECT detail_json, recipient_id FROM events WHERE id=?", (int(sys.argv[1]),)).fetchone()
d = json.loads(dj or "{}")
h = d.get("headers") or {}
print("recipient_id:", rid)
for k in ("message_id", "rfc_message_id", "msg_id"):
    if d.get(k):
        print(k, "=", d[k])
for k in ("Message-ID", "Message-Id", "Subject", "From"):
    if h.get(k):
        print(k, "=", h[k])
