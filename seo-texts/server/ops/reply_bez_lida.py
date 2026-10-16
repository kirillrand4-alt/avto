# -*- coding: utf-8 -*-
"""События reply за N дней, по которым нет лида (ни по адресу, ни по ИНН). Только чтение."""
import json, sqlite3, sys, time
дн = int(sys.argv[1]) if len(sys.argv) > 1 else 14
от = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - дн * 86400))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
лид_адр = {str(r[0]).lower() for r in c.execute("SELECT email FROM leads")}
лид_инн = {str(r[0]) for r in c.execute("SELECT inn FROM leads WHERE inn IS NOT NULL")}
n = 0
for ts, rid, em, inn, name, dj, mb in c.execute(
        "SELECT e.event_ts, e.recipient_id, r.email, r.inn, r.company_name, e.detail_json, e.mailbox_id FROM events e "
        "LEFT JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type='reply' AND e.event_ts>=?", (от,)):
    d = json.loads(dj or "{}")
    отк = str(d.get("from") or d.get("ot") or "").lower()
    if str(em or "").lower() in лид_адр or str(inn or "") in лид_инн or (отк and any(a in отк for a in лид_адр)):
        continue
    n += 1
    print(ts[:16], mb, "|", em, inn, name, "| от:", отк[:60], "|", str(d.get("kind") or d.get("snippet") or "")[:80])
print("reply без лида:", n)
