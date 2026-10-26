# -*- coding: utf-8 -*-
"""Последние отправки (письма и ответы) и разбивка за последний час по 10 минут. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: ("meyer" if "meyer" in str(r[1]).lower() else "kc") for r in c.execute("SELECT id, name FROM campaigns")}
print("последнее письмо:", c.execute("SELECT MAX(sent_at) FROM messages WHERE status='sent'").fetchone())
print("последний ответ:", c.execute("SELECT MAX(event_ts) FROM events WHERE event_type='reply_sent'").fetchone())
from collections import Counter
сч = Counter()
for cid, ts in c.execute("SELECT campaign_id, sent_at FROM messages WHERE status='sent' AND sent_at >= datetime('now','-90 minutes')"):
    сч[(ts[11:15] + "0", кам.get(cid))] += 1
for k in sorted(сч):
    print(k, сч[k])
print("тик автоотправки (настройка/состояние):", c.execute("SELECT key, substr(value,1,120) FROM panel_settings WHERE key LIKE '%auto%'").fetchall())
