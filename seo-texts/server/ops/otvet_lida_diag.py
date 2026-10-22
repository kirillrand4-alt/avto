# -*- coding: utf-8 -*-
"""Ушёл ли ручной ответ по лиду (владелец 22.10: «писал вручную ответ, вчера
уходили, сегодня плашка»): карточки confirm по адресу/ИНН лида (kind, статус,
кто, когда, начало текста), события reply/reply_sent, send_log — сегодня.
    otvet_lida_diag.py <lead_id>"""
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
л = c.execute("SELECT id, email, inn, recipient_id, created_at FROM leads WHERE id=?", (int(sys.argv[1]),)).fetchone()
print("лид:", л)
_, em, inn, rid, _ = л
кол = [r[1] for r in c.execute("PRAGMA table_info(confirm_reviews)")]
поля = [k for k in ("id", "kind", "status", "reason", "decided_by", "created_at", "decided_at", "email", "subject", "message_id") if k in кол]
for r in c.execute("SELECT %s, substr(body,1,140) FROM confirm_reviews WHERE (lower(email) LIKE ? OR inn=?) ORDER BY id DESC LIMIT 8"
                   % ",".join(поля), ("%" + em.split("@")[-1].lower(), inn)):
    print("карточка:", dict(zip(поля + ["тело"], r)))
for r in c.execute("SELECT e.id, e.event_type, e.event_ts, substr(e.detail_json,1,200) FROM events e JOIN recipients r ON r.id=e.recipient_id "
                   "WHERE r.inn=? AND e.event_ts>='2026-10-21' ORDER BY e.id", (inn,)):
    print("событие:", r)
for r in c.execute("SELECT ts, email, subject, outcome FROM send_log WHERE inn=? AND ts>='2026-10-21'", (inn,)):
    print("send_log:", r)
print("\nручные ответы (reply_sent) по всем лидам за 2 дня, по дням:",
      c.execute("SELECT substr(event_ts,1,10), COUNT(*) FROM events WHERE event_type='reply_sent' AND event_ts>='2026-10-21' GROUP BY 1").fetchall())
print("карточки kind=reply за 2 дня по статусу:",
      c.execute("SELECT substr(created_at,1,10), status, COUNT(*) FROM confirm_reviews WHERE kind='reply' AND created_at>='2026-10-21' GROUP BY 1,2").fetchall())
