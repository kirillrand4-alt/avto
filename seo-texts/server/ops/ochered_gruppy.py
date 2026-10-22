# -*- coding: utf-8 -*-
"""Очередь по группам (ящик, пояс получателя) x вердикт и что ушло после
момента T по тем же группам и кампаниям. Только чтение. ochered_gruppy.py [T]"""
import sqlite3
import sys
from collections import Counter, defaultdict

T = sys.argv[1] if len(sys.argv) > 1 else "2026-10-22T03:38"
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
оч = defaultdict(Counter)
мин = {}
for em, sa, mb, tz in c.execute("SELECT lower(r.email), m.scheduled_at, m.mailbox_id, r.tz FROM messages m JOIN recipients r "
                                "ON r.id=m.recipient_id WHERE m.status='scheduled'"):
    в = проба.get(em, "") or "не проверен"
    оч[(mb, tz)][в] += 1
    мин[(mb, tz, в)] = min(мин.get((mb, tz, в), "9"), str(sa)[:16])
print("ОЧЕРЕДЬ (ящик, пояс): вердикт=штук (самое раннее время)")
for k, v in оч.items():
    print("  ", k, {в: "%d (%s)" % (n, мин[(k[0], k[1], в)]) for в, n in v.items()})
у = Counter()
for em, cid, tz, sa in c.execute("SELECT lower(r.email), m.campaign_id, r.tz, m.sent_at FROM messages m JOIN recipients r "
                                 "ON r.id=m.recipient_id WHERE m.status='sent' AND m.sent_at>=?", (T,)):
    у[(кам.get(cid, cid), tz, проба.get(em, "") or "не проверен")] += 1
print("\nУШЛО после", T)
for k, v in sorted(у.items()):
    print("  %3d  %s" % (v, k))
