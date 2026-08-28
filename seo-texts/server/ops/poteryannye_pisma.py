# -*- coding: utf-8 -*-
"""Потери на стороне базы: где письмо или ответ застряли между звеньями."""
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
сейчас = datetime.now(timezone.utc).isoformat()

print("=== 1. входящие БЕЗ привязки к получателю ===")
for r in c.execute(
        "SELECT event_type, COUNT(*) n, MIN(event_ts) с, MAX(event_ts) по "
        "  FROM events WHERE recipient_id IS NULL "
        "   AND event_type IN ('reply','reply_auto','other') GROUP BY 1"):
    print("   %-12s %4d  с %s по %s" % (r["event_type"], r["n"],
                                        str(r["с"])[:10], str(r["по"])[:10]))

print("")
print("=== 2. ответы клиентов БЕЗ карточки лида ===")
n = c.execute(
    "SELECT COUNT(*) FROM events e WHERE e.event_type IN ('reply','reply_auto') "
    "  AND e.recipient_id IS NOT NULL "
    "  AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.recipient_id=e.recipient_id)"
).fetchone()[0]
print("   ответов без лида: %d" % n)
for r in c.execute(
        "SELECT e.id, e.event_ts, e.event_type, rc.email, rc.company_name "
        "  FROM events e JOIN recipients rc ON rc.id=e.recipient_id "
        " WHERE e.event_type IN ('reply','reply_auto') "
        "   AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.recipient_id=e.recipient_id) "
        " ORDER BY e.event_ts DESC LIMIT 8"):
    print("      #%-7s %-11s %s %-26s %s"
          % (r["id"], r["event_type"], str(r["event_ts"])[:16],
             str(r["email"])[:26], str(r["company_name"] or "")[:26]))

print("")
print("=== 3. письма, застрявшие между статусами ===")
for r in c.execute("SELECT status, COUNT(*) n FROM messages GROUP BY 1 ORDER BY 2 DESC"):
    print("   %-16s %5d" % (r["status"], r["n"]))
n = c.execute("SELECT COUNT(*) FROM messages WHERE status='scheduled' "
              "   AND scheduled_at < ?", (сейчас,)).fetchone()[0]
print("   из них scheduled со слотом в прошлом: %d" % n)

print("")
print("=== 4. одобренные карточки, чьё письмо снято ===")
for r in c.execute(
        "SELECT m.status, COUNT(*) n FROM confirm_reviews cr "
        "  JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='approved' GROUP BY 1 ORDER BY 2 DESC"):
    print("   карточка approved -> письмо %-14s %4d" % (r["status"], r["n"]))

print("")
print("=== 5. карточки в очереди без письма (отправить нельзя) ===")
n = c.execute("SELECT COUNT(*) FROM confirm_reviews "
              " WHERE status='pending' AND message_id IS NULL "
              "   AND COALESCE(kind,'outbound')<>'reply'").fetchone()[0]
print("   pending без message_id: %d" % n)

print("")
print("=== 6. лиды без события-ответа (осиротевшие) ===")
n = c.execute(
    "SELECT COUNT(*) FROM leads l WHERE l.recipient_id IS NOT NULL "
    "  AND NOT EXISTS (SELECT 1 FROM events e WHERE e.recipient_id=l.recipient_id "
    "                    AND e.event_type IN ('reply','reply_auto','other'))"
).fetchone()[0]
print("   лидов без входящего события: %d" % n)
c.close()
