# -*- coding: utf-8 -*-
"""Отбивки за сутки (владелец 22.10: «баунсы так и продолжают лететь»): когда
ушло письмо (до/после перестановки очереди), какой вердикт пробы был у адреса
ДО отбивки (история obzvon-index.email_probe), и что ушло после перестановки.
    baunsy_segodnya.py [с_какого YYYY-MM-DD] [перестановка_utc]"""
import json
import re
import sqlite3
import sys
from collections import Counter

от = sys.argv[1] if len(sys.argv) > 1 else "2026-10-21T21:00"
перест = sys.argv[2] if len(sys.argv) > 2 else "2026-10-22T03:38"
c = sqlite3.connect(r"C:\sender\sender.db")
о = sqlite3.connect(r"C:\sender\obzvon-index.db")
ист = {}
for em, v, src, ts in о.execute("SELECT lower(email), verdict, source, ts FROM email_probe ORDER BY ts"):
    ист.setdefault(em, []).append((str(ts)[:16], v, src))
проба = {str(r[0]).lower(): (r[1], str(r[2])[:16], r[3]) for r in c.execute("SELECT email, verdict, ts, source FROM addr_probe")}
сч = Counter()
print("ОТБИВКИ с", от)
for et, dj, em, sa, mb in c.execute(
        "SELECT e.event_ts, e.detail_json, lower(r.email), m.sent_at, m.mailbox_id FROM events e "
        "LEFT JOIN recipients r ON r.id=e.recipient_id LEFT JOIN messages m ON m.id=e.message_id "
        "WHERE e.event_type='bounce' AND e.event_ts>=? ORDER BY e.event_ts", (от,)):
    д = json.loads(dj or "{}")
    диаг = str((д.get("dsn") or {}).get("diagnostic") or д.get("error") or "")[:70]
    до = [h for h in ист.get(em, []) if "bounce" not in str(h[2])]
    было = до[-1][1] if до else "не проверен (только по отбивке)"
    когда = "после перест." if str(sa or "") >= перест else "до перест."
    сч[(когда, было)] += 1
    print("  %s | ушло %s %s | %-34s | до отбивки: %-14s | %s" % (str(et)[:16], str(sa)[:16], когда, em[:34], было, re.sub(r"\s+", " ", диаг)))
print("\nсводка (когда ушло, вердикт до отбивки):")
for k, v in сч.most_common():
    print("  %3d  %s" % (v, k))
у = Counter()
for em, sa in c.execute("SELECT lower(r.email), m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                        "WHERE m.status='sent' AND m.sent_at>=?", (перест,)):
    до = [h for h in ист.get(em, []) if "bounce" not in str(h[2])]
    у[до[-1][1] if до else (проба.get(em, ("не проверен",))[0])] += 1
print("\nушло после перестановки (%s) по вердикту: %s" % (перест, dict(у)))
