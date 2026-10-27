# -*- coding: utf-8 -*-
"""Темы писем со склеенным словом («компрессорамв», «оборудованиюдля»): сколько,
по статусам и кампаниям, примеры. Только чтение."""
import re
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
РЕГ = re.compile(r"(компрессорам|оборудованию|сжатому воздуху|контролю качества|сортировке)(в|для|на)\b", re.I)
сч, прим = Counter(), Counter()
for mid, cid, st, subj in c.execute("SELECT m.id, m.campaign_id, m.status, coalesce(cr.subject, m.subject) FROM messages m "
                                    "LEFT JOIN confirm_reviews cr ON cr.message_id=m.id"):
    if subj and РЕГ.search(subj):
        сч[(st, кам.get(cid))] += 1
        прим[РЕГ.search(subj).group(0)] += 1
for k, n in сч.most_common():
    print(n, k)
print(прим.most_common(10))
