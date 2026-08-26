# -*- coding: utf-8 -*-
"""Привязать ответ «Шато де Талю» к компании: событие, карточка, лид.

Ответ пришёл 19.08 в 11:30 с andryushchenko@chateaudetalu.ru, а писали мы
на sale@. Ветка не сошлась, привязки по домену тогда не было — событие
легло без получателя, а лид завёлся отдельной карточкой «вне переписки».

    python privyazat_shato.py            # показать
    python privyazat_shato.py primenit   # привязать
"""
import json
import sqlite3
import sys
import time

ДЕЛАТЬ = "primenit" in sys.argv[1:]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=90000")
c.row_factory = sqlite3.Row

rec = c.execute("SELECT id, email, company_name, inn FROM recipients "
                " WHERE email='sale@chateaudetalu.ru'").fetchone()
соб = c.execute("SELECT id, event_type, event_ts, recipient_id FROM events "
                " WHERE detail_json LIKE '%chateaudetalu%'").fetchall()
лид = c.execute("SELECT id, email, recipient_id, reply_kind, status FROM leads "
                " WHERE email LIKE '%chateaudetalu%'").fetchone()
письмо = c.execute("SELECT id, message_id FROM confirm_reviews "
                   " WHERE recipient_id=? ORDER BY id DESC LIMIT 1",
                   (rec["id"],)).fetchone() if rec else None
print("получатель: #%s %s (%s)" % (rec["id"], rec["email"], rec["company_name"]))
for s in соб:
    print("событие #%s %s %s получатель=%s"
          % (s["id"], s["event_type"], str(s["event_ts"])[:19], s["recipient_id"]))
print("лид #%s: %s | получатель=%s | %s | %s"
      % (лид["id"], лид["email"], лид["recipient_id"], лид["reply_kind"],
         лид["status"]) if лид else "лида нет")
print("письмо: карточка #%s, message_id %s"
      % (письмо["id"], письмо["message_id"]) if письмо else "письма нет")

if not ДЕЛАТЬ:
    print("\nвхолостую. Привязать — primenit")
    raise SystemExit(0)

сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
for s in соб:
    if s["recipient_id"] is None:
        c.execute("UPDATE events SET recipient_id=?, event_type='reply' "
                  " WHERE id=?", (rec["id"], s["id"]))
        print("событие #%s привязано и переведено в 'reply'" % s["id"])
if лид and лид["recipient_id"] is None:
    c.execute("UPDATE leads SET recipient_id=?, company=NULL, reply_kind=?, "
              "updated_at=? WHERE id=?"
              if False else
              "UPDATE leads SET recipient_id=?, reply_kind=?, updated_at=? "
              " WHERE id=?",
              (rec["id"], "hot", сейчас, лид["id"]))
    print("лид #%s привязан к получателю #%s, метка hot"
          % (лид["id"], rec["id"]))
c.commit()
c.close()
print("готово")
