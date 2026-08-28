# -*- coding: utf-8 -*-
"""Разбор баунсов по партиям вторых адресов."""
import io
import json
import sqlite3
from collections import Counter

партии = {}
for ф, п in ((r"C:\sender\_ops\vtorye-adresa.jsonl", 1),
             (r"C:\sender\_ops\vtorye-adresa-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                партии[int(d["review"])] = п
    except FileNotFoundError:
        pass
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партии))
# получатели партий
rids = {}
for r in c.execute("SELECT id, recipient_id, email FROM confirm_reviews "
                   " WHERE id IN (%s)" % зн, list(партии)):
    if r["recipient_id"]:
        rids[int(r["recipient_id"])] = (int(r["id"]), r["email"])
print("получателей в партиях: %d" % len(rids))
print("отправлено из партий: %d" % c.execute(
    "SELECT COUNT(*) FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE cr.id IN (%s) AND m.status='sent'" % зн, list(партии)).fetchone()[0])

зн2 = ",".join("?" * len(rids))
print("")
print("=== события по получателям партий за сегодня ===")
for r in c.execute(
        "SELECT event_type, COUNT(*) FROM events "
        " WHERE recipient_id IN (%s) AND substr(event_ts,1,10)=date('now') "
        " GROUP BY 1 ORDER BY 2 DESC" % зн2, list(rids)):
    print("   %-16s %4d" % (r[0], r[1]))
print("")
print("=== баунсы: подробно ===")
for r in c.execute(
        "SELECT e.*, rc.email pochta "
        "  FROM events e LEFT JOIN recipients rc ON rc.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND e.recipient_id IN (%s) "
        " ORDER BY e.event_ts DESC LIMIT 12" % зн2, list(rids)):
    к = r.keys()
    д = str(r["detail_json"] if "detail_json" in к else
            (r["payload_json"] if "payload_json" in к else ""))
    print("   %-30s %s  ящик %s" % (str(r["pochta"])[:30],
                                    str(r["event_ts"])[:16],
                                    r["mailbox_id"] if "mailbox_id" in к else "?"))
    print("      %s" % д[:200])
print("")
print("=== баунсы по всей базе за сегодня ===")
for r in c.execute(
        "SELECT COUNT(*) n FROM events WHERE event_type='bounce' "
        "   AND substr(event_ts,1,10)=date('now')"):
    print("   всего: %d" % r[0])
c.close()
