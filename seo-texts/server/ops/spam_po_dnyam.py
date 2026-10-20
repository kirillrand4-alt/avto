# -*- coding: utf-8 -*-
"""Отказы «спам» (сервер получателя не пустил письмо как спам) по дням и
кампаниям за N суток (по умолч. 7), плюс сколько отправлено в те же дни.
    spam_po_dnyam.py [N]"""
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
N = int(sys.argv[1]) if len(sys.argv) > 1 else 7
от = (datetime.utcnow() - timedelta(days=N)).strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
отпр = Counter((str(r[0])[:10], кам.get(r[1], r[1])) for r in c.execute(
    "SELECT sent_at, campaign_id FROM messages WHERE status='sent' AND sent_at>=?", (от,)))
спам = defaultdict(list)
for ts, cid, mid, dj, em in c.execute(
        "SELECT e.event_ts, COALESCE(e.campaign_id, m.campaign_id), e.message_id, e.detail_json, r.email FROM events e "
        "LEFT JOIN messages m ON m.id=e.message_id LEFT JOIN recipients r ON r.id=e.recipient_id "
        "WHERE e.event_type IN ('bounce','failed') AND e.event_ts>=?", (от,)):
    d = json.loads(dj or "{}")
    диаг = str((d.get("dsn") or {}).get("diagnostic") or d.get("error") or "")
    if re.search(r"(?i)spam|спам|5\.7\.1", диаг):
        спам[(str(ts)[:10], кам.get(cid, cid))].append((em, диаг[:110]))
print("день        кампания                        отправлено  спам-отказов")
for к in sorted(set(отпр) | set(спам)):
    print("%s  %-32s %6d %6d" % (к[0], str(к[1])[:32], отпр.get(к, 0), len(спам.get(к, []))))
print("\nвсего спам-отказов:", sum(len(v) for v in спам.values()))
for к, v in sorted(спам.items()):
    for em, д in v[:3]:
        print("  ", к[0], em, "|", д)
