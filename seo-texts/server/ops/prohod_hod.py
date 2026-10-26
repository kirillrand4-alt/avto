# -*- coding: utf-8 -*-
"""Что делает проход автоотправки с момента рестарта: письма, тронутые после T. Только чтение.
    prohod_hod.py <T UTC, напр. 2026-10-26T09:17>"""
import sqlite3
import sys
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
T = sys.argv[1]
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сч = Counter()
for st, cid, err, sch in c.execute("SELECT status, campaign_id, coalesce(last_error,''), scheduled_at FROM messages WHERE updated_at>=?", (T,)):
    сч[(st, кам.get(cid, "?")[:22], err[:40], "перенос>сейчас" if sch and sch > T[:10] + "T23" else "")] += 1
for k, n in сч.most_common(20):
    print(n, k)
print("sending всего:", c.execute("SELECT COUNT(*) FROM messages WHERE status='sending'").fetchone()[0])
