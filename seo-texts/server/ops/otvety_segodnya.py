# -*- coding: utf-8 -*-
"""Ответы за последние N часов (по умолч. 24): события reply/reply_auto по
кампаниям и ящикам, лиды, созданные за то же время, и входящие, которые не
привязались к письму. Только чтение.  otvety_segodnya.py [N]"""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta

N = int(sys.argv[1]) if len(sys.argv) > 1 else 24
от = (datetime.utcnow() - timedelta(hours=N)).strftime("%Y-%m-%dT%H:%M:%S")
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
таб = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
print("с", от, "UTC")
сч = Counter()
for et, cid, mid in c.execute("SELECT ev.event_type, COALESCE(ev.campaign_id, m.campaign_id), ev.message_id FROM events ev "
                              "LEFT JOIN messages m ON m.id=ev.message_id WHERE ev.event_type IN ('reply','reply_auto') AND ev.event_ts>=?", (от,)):
    сч[(et, кам.get(cid, cid))] += 1
print("события ответов по кампаниям:")
for k, v in sorted(сч.items(), key=lambda x: -x[1]):
    print("  %-11s %-32s %4d" % (k[0], str(k[1])[:32], v))
if "leads" in таб:
    кол = {r[1] for r in c.execute("PRAGMA table_info(leads)")}
    тс = next((k for k in ("created_at", "ts", "first_reply_at", "updated_at") if k in кол), None)
    if тс:
        print("лиды за период по виду:", dict(c.execute("SELECT reply_kind, COUNT(*) FROM leads WHERE %s>=? GROUP BY reply_kind" % тс, (от,)).fetchall()))
        print("лиды за период по статусу:", dict(c.execute("SELECT status, COUNT(*) FROM leads WHERE %s>=? GROUP BY status" % тс, (от,)).fetchall()))
for т in ("inbound", "inbound_messages", "inbox", "replies", "mail_in"):
    if т in таб:
        кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
        print("таблица", т, кол[:15])
        тс = next((k for k in ("received_at", "ts", "created_at", "date") if k in кол), None)
        if тс:
            print("  за период:", c.execute("SELECT COUNT(*) FROM %s WHERE %s>=?" % (т, тс), (от,)).fetchone()[0])
            if "matched" in кол or "message_id" in кол:
                к = "matched" if "matched" in кол else "message_id"
                print("  не привязано к письму:", c.execute("SELECT COUNT(*) FROM %s WHERE %s>=? AND (%s IS NULL OR %s=0)" % (т, тс, к, к), (от,)).fetchone()[0])
print("все типы событий за период:", dict(c.execute("SELECT event_type, COUNT(*) FROM events WHERE event_ts>=? GROUP BY event_type", (от,)).fetchall()))
