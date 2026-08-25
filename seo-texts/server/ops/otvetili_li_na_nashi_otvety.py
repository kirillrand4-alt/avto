# -*- coding: utf-8 -*-
"""Ответил ли кто-нибудь на НАШИ ответы: сверка по времени, а не на глаз.

Берём каждый наш ответ клиенту и смотрим, приходило ли от этой компании
что-нибудь ПОСЛЕ него. Ответ на предыдущее письмо не считается — у панели
метка «ответили» стоит по компании, а не по письму, и легко обманывает.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

наши = c.execute(
    "SELECT ев.id, ев.event_ts, ев.recipient_id, ев.message_id, "
    "       r.company_name, r.email, r.inn FROM events ев "
    "  LEFT JOIN recipients r ON r.id=ев.recipient_id "
    " WHERE ев.event_type='reply_sent' ORDER BY ев.event_ts").fetchall()
print("наших ответов клиентам: %d\n" % len(наши))

итог = Counter()
for о in наши:
    # Ищем строго: по получателю и по ПОЛНОМУ адресу в заголовках. Поиск
    # по домену давал ложные срабатывания — «bk.ru» и «mail.ru» стоят у
    # доброй половины базы, и любое чужое письмо считалось бы ответом.
    после = c.execute(
        "SELECT COUNT(*) FROM events "
        " WHERE event_type IN ('reply','reply_auto','other') "
        "   AND event_ts > ? "
        "   AND (recipient_id = ? OR detail_json LIKE ?)",
        (о["event_ts"], о["recipient_id"],
         "%" + str(о["email"] or "нетакогоадреса@нет").strip().lower() + "%")
        ).fetchone()[0]
    # Что именно пришло — чтобы не гадать по счётчику.
    свежие = c.execute(
        "SELECT event_ts, event_type, substr(detail_json,1,0) FROM events "
        " WHERE event_type IN ('reply','reply_auto','other') AND event_ts > ? "
        "   AND recipient_id = ? ORDER BY event_ts LIMIT 1",
        (о["event_ts"], о["recipient_id"])).fetchone()
    метка = "ОТВЕТИЛИ" if после else "тишина"
    итог[метка] += 1
    print("   %-9s %s | %-30s %-26s %s"
          % (метка, str(о["event_ts"])[:16],
             str(о["company_name"] or "-")[:30], str(о["email"] or "-")[:26],
             ("пришло %s %s" % (str(свежие["event_ts"])[:16], свежие["event_type"]))
             if свежие else ""))

print("\n=== ИТОГ ===")
for к, н in итог.most_common():
    print("   %-12s %3d" % (к, н))
print("\nсамый свежий наш ответ: %s"
      % (str(наши[-1]["event_ts"])[:19] if наши else "нет"))
