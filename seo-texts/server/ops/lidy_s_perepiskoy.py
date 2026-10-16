# -*- coding: utf-8 -*-
"""Лиды в «не интересно», с кем велась переписка (наш ответ из панели или из почты,
либо их повторные ответы). Не трогаем компании с лидом в Bitrix.
--perenesti переводит их в perepiska (через LeadDesk, с событием)."""
import sqlite3, sys
from collections import defaultdict
sys.path.insert(0, r"C:\sender")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.row_factory = sqlite3.Row
табл = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
ev = next(t for t in табл if t in ("events", "event_log", "mail_events"))
кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % ev)]
print("события:", ev, кол)
import json
наш = defaultdict(int)
for r in c.execute("SELECT e.event_type, e.detail_json, r.email FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
                   "WHERE e.event_type IN ('reply_sent','manual_reply')"):
    try: d = json.loads(r["detail_json"] or "{}")
    except ValueError: d = {}
    for a in {str(d.get("komu") or "").lower(), str(r["email"] or "").lower()} - {""}:
        наш[a] += 1
дописан = defaultdict(int)
for r in c.execute("SELECT lead_id FROM lead_events WHERE action='дописан ответ'"):
    дописан[r["lead_id"]] += 1
# их ответы: событий reply по адресу больше одного = переписка шла
пан = defaultdict(int)
for r in c.execute("SELECT lower(r.email) e FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type='reply'"):
    пан[r["e"]] += 1
битрикс = {str(r[0]) for r in c.execute("SELECT inn FROM leads WHERE status='in_bitrix' AND inn IS NOT NULL")}
итог = []
for r in c.execute("SELECT id, inn, email, company_name FROM leads WHERE status='not_interested'"):
    e = str(r["email"] or "").lower()
    if str(r["inn"] or "") in битрикс: continue
    п = []
    if наш.get(e): п.append("наш ответ %d" % наш[e])
    if пан.get(e, 0) > 1: п.append("их ответов %d" % пан[e])
    if дописан.get(r["id"]): п.append("их повторный ответ %d" % дописан[r["id"]])
    if п: итог.append((r["id"], r["company_name"], e, ", ".join(п)))
print("всего в «не интересно»:", c.execute("SELECT COUNT(*) FROM leads WHERE status='not_interested'").fetchone()[0], "| с перепиской:", len(итог))
for x in итог: print("  #%s %s <%s> — %s" % x)
if "--perenesti" in sys.argv and итог:
    import time
    т = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    with c:
        for x in итог:
            n = c.execute("UPDATE leads SET status='perepiska', version=version+1, updated_at=? WHERE id=? AND status='not_interested'", (т, x[0])).rowcount
            if n:
                c.execute("INSERT INTO lead_events (lead_id, action, from_status, to_status, detail_json, created_at) VALUES (?, 'status_changed', 'not_interested', 'perepiska', '{\"status\": \"perepiska\", \"pochemu\": \"велась переписка, владелец 16.10\"}', ?)", (x[0], т))
    print("перенесено в «ведётся переписка»:", len(итог))
