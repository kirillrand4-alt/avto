# -*- coding: utf-8 -*-
"""Воронка: отправлено → входящих → ответов → карточек лидов.

Владелец: «странно что в 2 раза меньше ответов». Ящики сошлись, значит
теряется не письмо, а шаг после него. Считаем каждый шаг.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

всего = c.execute("SELECT COUNT(*) FROM messages WHERE sent_at IS NOT NULL"
                  ).fetchone()[0]
print("отправлено писем всего: %d" % всего)
print("")
print("=== входящие события по видам ===")
for r in c.execute("SELECT event_type, COUNT(*) n FROM events "
                   " WHERE event_type IN ('reply','reply_auto','other',"
                   "'complaint','bounce') GROUP BY event_type ORDER BY n DESC"):
    print("   %-12s %d" % (r["event_type"], r["n"]))

ответы = c.execute("SELECT COUNT(*) FROM events WHERE event_type IN "
                   "('reply','reply_auto')").fetchone()[0]
скольких = c.execute("SELECT COUNT(DISTINCT recipient_id) FROM events "
                     " WHERE event_type IN ('reply','reply_auto') "
                     "   AND recipient_id IS NOT NULL").fetchone()[0]
лидов = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
слидом = c.execute("SELECT COUNT(DISTINCT recipient_id) FROM leads "
                   " WHERE recipient_id IS NOT NULL").fetchone()[0]
print("")
print("ответов (reply+reply_auto): %d от %d компаний" % (ответы, скольких))
print("карточек лидов: %d по %d компаниям" % (лидов, слидом))

print("")
print("=== компании, ответившие, но БЕЗ карточки лида ===")
ряды = c.execute(
    "SELECT e.recipient_id, r.company_name, r.email, COUNT(*) n, "
    "       MAX(e.event_ts) когда "
    "  FROM events e JOIN recipients r ON r.id=e.recipient_id "
    " WHERE e.event_type IN ('reply','reply_auto') "
    "   AND e.recipient_id NOT IN (SELECT COALESCE(recipient_id,-1) FROM leads) "
    " GROUP BY e.recipient_id ORDER BY когда DESC").fetchall()
print("таких: %d" % len(ряды))
for r in ряды[:25]:
    print("   %-34s %-30s ответов %d, последний %s"
          % (str(r["company_name"])[:34], str(r["email"])[:30], r["n"],
             str(r["когда"])[:16]))
c.close()
