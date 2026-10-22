# -*- coding: utf-8 -*-
"""Полный текст входящих ответов получателя лида (events reply, тело из
detail_json). Только чтение. otvet_polnyy.py <lead_id>"""
import json
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
rid = c.execute("SELECT recipient_id FROM leads WHERE id=?", (int(sys.argv[1]),)).fetchone()[0]
for eid, ts, dj in c.execute("SELECT id, event_ts, detail_json FROM events WHERE recipient_id=? AND event_type='reply' ORDER BY id", (rid,)):
    d = json.loads(dj or "{}")
    тело = d.get("body") or d.get("text") or d.get("snippet") or ""
    if not тело:
        for k, v in d.items():
            if isinstance(v, str) and len(v) > len(тело) and k != "headers":
                тело = v
    print("=== событие %s %s" % (eid, ts))
    print(str(тело)[:5000])
