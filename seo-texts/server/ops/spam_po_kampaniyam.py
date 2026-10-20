# -*- coding: utf-8 -*-
"""Спам по кампаниям за всё время (владелец 20.10: «было в старом стиле много
спам?»): отправлено; Яндекс не выпустил («suspicion of SPAM» в last_error);
отказы получателей с признаком спама/репутации (bounce 5.7.1/spam/blocked IP)."""
import json
import re
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
отпр = Counter(r[0] for r in c.execute("SELECT campaign_id FROM messages WHERE status='sent'"))
ян = Counter(r[0] for r in c.execute("SELECT campaign_id FROM messages WHERE last_error LIKE '%suspicion of SPAM%'"))
пол = Counter()
for cid, dj in c.execute("SELECT COALESCE(e.campaign_id, m.campaign_id), e.detail_json FROM events e "
                         "LEFT JOIN messages m ON m.id=e.message_id WHERE e.event_type IN ('bounce','failed')"):
    d = json.loads(dj or "{}")
    диаг = str((d.get("dsn") or {}).get("diagnostic") or d.get("error") or "")
    if re.search(r"(?i)spam|спам|IP you're using|blocked|blacklist|client host|5\.7\.1 service unavailable", диаг) \
            and not re.search(r"(?i)recipient address|5\.7\.133|authentication required", диаг):
        пол[cid] += 1
print("%-34s %7s %8s %8s" % ("кампания", "ушло", "Яндекс", "получат."))
for cid in sorted(отпр, key=lambda k: -отпр[k]):
    if отпр[cid] < 20:
        continue
    n = отпр[cid]
    print("%-34s %7d %5d %4.1f%% %5d %4.1f%%" % (str(кам.get(cid, cid))[:34], n, ян[cid], 100 * ян[cid] / (n + ян[cid]),
                                              пол[cid], 100 * пол[cid] / n))
