# -*- coding: utf-8 -*-
"""Что лежит в событиях «other»: их 165 — больше, чем ответов.

«other» — это входящее, которое сторож не признал ответом: нет
In-Reply-To/References. Но если письмо ПРИВЯЗАНО к нашему получателю, оно
почти наверняка ответ — просто человек нажал «написать», а не «ответить».
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

всего = c.execute("SELECT COUNT(*) FROM events WHERE event_type='other'"
                  ).fetchone()[0]
с_получателем = c.execute(
    "SELECT COUNT(*) FROM events WHERE event_type='other' "
    "  AND recipient_id IS NOT NULL").fetchone()[0]
print("событий «other»: %d, из них привязаны к получателю: %d"
      % (всего, с_получателем))

print("")
print("=== привязанные «other» — есть ли у них карточка лида ===")
ряды = c.execute(
    "SELECT e.id, e.event_ts, e.recipient_id, e.detail_json, "
    "       r.company_name, r.email, "
    "       (SELECT COUNT(*) FROM leads l WHERE l.recipient_id=e.recipient_id) лид "
    "  FROM events e JOIN recipients r ON r.id=e.recipient_id "
    " WHERE e.event_type='other' ORDER BY e.event_ts DESC").fetchall()
без_лида = [r for r in ряды if not r["лид"]]
print("всего %d, БЕЗ карточки лида: %d" % (len(ряды), len(без_лида)))
print("")
for r in ряды[:30]:
    d = json.loads(r["detail_json"] or "{}")
    т = " ".join(str(d.get("snippet") or "").split())[:88]
    print("   %s %-28s %-26s лид:%s"
          % (str(r["event_ts"])[:16], str(r["company_name"])[:28],
             str(r["email"])[:26], "есть" if r["лид"] else "НЕТ"))
    print("      %s" % т)
c.close()
