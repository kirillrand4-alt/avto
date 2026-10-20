# -*- coding: utf-8 -*-
"""Ошибки самой отправки за N суток (по умолч. 3): письма с last_error по статусам и
видам (что ответил наш SMTP — Яндекс), события failed, ящики."""
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
от = (datetime.utcnow() - timedelta(days=N)).strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
сч, ящ, прим = Counter(), Counter(), {}
for st, e, mb in c.execute("SELECT status, last_error, mailbox_id FROM messages WHERE updated_at>=? AND last_error IS NOT NULL AND last_error!=''", (от,)):
    e = str(e)
    if e.startswith("снято") or "дубль" in e:
        continue
    к = re.sub(r"[\d<>@\[\]().,:;'\"-]+", " ", e)[:60].strip()
    сч[(st, к)] += 1
    ящ[mb] += 1
    прим.setdefault(к, e[:220])
print("письма с ошибкой отправки (кроме снятых вручную):", sum(сч.values()))
for k, v in сч.most_common(12):
    print("  %4d %s" % (v, k))
print("примеры:")
for к, e in list(прим.items())[:8]:
    print("   ", e)
print("ящики:", ящ.most_common(10))
ф = Counter(str(r[0])[:10] for r in c.execute("SELECT event_ts FROM events WHERE event_type='failed' AND event_ts>=?", (от,)))
print("события failed по дням:", dict(sorted(ф.items())))
