# -*- coding: utf-8 -*-
"""Лид целиком (все поля, кроме длинного текста — первые 200 знаков) и
события reply по его получателю. Только чтение. lid_podrobno.py <id>"""
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
л = c.execute("SELECT * FROM leads WHERE id=?", (int(sys.argv[1]),)).fetchone()
for k in л.keys():
    if л[k] not in (None, ""):
        print("  %-22s %s" % (k, str(л[k]).replace("\n", " ")[:200]))
for r in c.execute("SELECT id, event_type, event_ts, campaign_id FROM events WHERE recipient_id=? AND event_type LIKE 'reply%' ORDER BY id",
                   (л["recipient_id"],)):
    print("  событие", tuple(r))
