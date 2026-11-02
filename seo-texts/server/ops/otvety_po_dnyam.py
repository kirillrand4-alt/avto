# -*- coding: utf-8 -*-
"""По дням (UTC) за 14 дней: отправлено по направлению/кампании, отбивки, лиды по типам. Только чтение."""
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
print("отправлено по дням и кампаниям:")
for r in c.execute("SELECT substr(ts,1,10) d, campaign_id, count(*) FROM send_log WHERE outcome='sent' AND ts>=date('now','-14 days') GROUP BY 1,2 ORDER BY 1,2"):
    print("  ", r)
print("лиды по дням и статусам:")
for r in c.execute("SELECT substr(created_at,1,10), status, count(*) FROM leads WHERE created_at>=date('now','-14 days') GROUP BY 1,2 ORDER BY 1"):
    print("  ", r)
print("отбивки по дням:")
for r in c.execute("SELECT substr(event_ts,1,10), event_type, count(*) FROM events WHERE event_ts>=date('now','-14 days') AND event_type IN ('bounce','hard_bounce','soft_bounce','complaint','reply','auto_reply') GROUP BY 1,2 ORDER BY 1"):
    print("  ", r)
print("кампании:", c.execute("SELECT id, name FROM campaigns WHERE id>=10").fetchall())
