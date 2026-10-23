# -*- coding: utf-8 -*-
"""Итог кампании: отправлено (по дням), уникальных компаний, отбивки, ответы
по видам, лиды по статусам (в т.ч. отданные в Bitrix). Только чтение.
    kampaniya_itog.py <campaign_id>"""
import sqlite3
import sys
from collections import Counter

cid = int(sys.argv[1])
c = sqlite3.connect(r"C:\sender\sender.db")
print("кампания:", c.execute("SELECT name FROM campaigns WHERE id=?", (cid,)).fetchone())
дни = c.execute("SELECT substr(sent_at,1,10), COUNT(*) FROM messages WHERE campaign_id=? AND status='sent' GROUP BY 1 ORDER BY 1", (cid,)).fetchall()
print("отправлено:", sum(n for _, n in дни), "| по дням:", дни)
print("компаний (ИНН):", c.execute("SELECT COUNT(DISTINCT r.inn) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                   "WHERE m.campaign_id=? AND m.status='sent'", (cid,)).fetchone()[0])
ев = Counter(dict(c.execute("SELECT event_type, COUNT(*) FROM events WHERE campaign_id=? GROUP BY 1", (cid,)).fetchall()))
print("события:", dict(ев))
ид = [r[0] for r in c.execute("SELECT DISTINCT recipient_id FROM messages WHERE campaign_id=? AND status='sent'", (cid,))]
q = ",".join(map(str, ид)) or "0"
print("лиды по статусам:", c.execute("SELECT status, COUNT(*) FROM leads WHERE recipient_id IN (%s) GROUP BY 1 ORDER BY 2 DESC" % q).fetchall())
print("лиды по виду ответа:", c.execute("SELECT reply_kind, COUNT(*) FROM leads WHERE recipient_id IN (%s) GROUP BY 1 ORDER BY 2 DESC" % q).fetchall())
