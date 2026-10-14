# -*- coding: utf-8 -*-
"""Покрытие пробой: письма в очереди подтверждения (pending) и в расписании
(scheduled) — есть ли у адреса вердикт пробы, какой. Только чтение."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
вердикт = {str(e).lower(): v for e, v in c.execute("SELECT email, verdict FROM addr_probe")}
for имя, sql in (
        ("очередь подтверждения", "SELECT lower(email), campaign_id FROM confirm_reviews WHERE status='pending'"),
        ("в расписании (scheduled)", "SELECT lower(r.email), m.campaign_id FROM messages m JOIN recipients r "
                                     "ON r.id=m.recipient_id WHERE m.status='scheduled'")):
    св = Counter()
    for em, камп in c.execute(sql):
        св[вердикт.get(em, "НЕ ПРОВЕРЕН")] += 1
    print("%s: всего %d — %s" % (имя, sum(св.values()), dict(св.most_common())))
print("свежесть: последняя проба", c.execute("SELECT max(ts) FROM addr_probe").fetchone()[0])
print("=== ПОКРЫТИЕ ПРОБОЙ ===")
