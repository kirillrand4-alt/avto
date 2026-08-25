# -*- coding: utf-8 -*-
"""Вся переписка с «Росткраном» по порядку: что писали мы и что ответили они."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
рек = c.execute("SELECT id, email, company_name, inn FROM recipients "
                " WHERE email LIKE '%rostkran%'").fetchall()
for р in рек:
    print("получатель #%s %s | %s | ИНН %s"
          % (р["id"], р["email"], р["company_name"], р["inn"]))
ид = [р["id"] for р in рек]
места = ",".join("?" * len(ид)) or "NULL"

события = []
for р in c.execute(
        "SELECT id, event_ts, event_type, detail_json FROM events "
        " WHERE recipient_id IN (%s) OR detail_json LIKE '%%rostkran%%' "
        " ORDER BY event_ts" % места, ид):
    события.append(("событие", р["event_ts"], р["event_type"],
                    json.loads(р["detail_json"] or "{}")))
письма = []
for р in c.execute(
        "SELECT id, status, sent_at, mailbox_id, subject, body_rendered "
        "  FROM messages WHERE recipient_id IN (%s) ORDER BY sent_at" % места, ид):
    письма.append(("письмо", р["sent_at"], р["status"], dict(р)))

for вид, когда, что, данные in sorted(письма + события,
                                      key=lambda x: str(x[1] or "")):
    print("\n=== %s %s | %s" % (str(когда)[:19], вид, что))
    if вид == "письмо":
        print("   с ящика: %s" % данные.get("mailbox_id"))
        print("   тема:    %s" % str(данные.get("subject") or "")[:90])
        тело = " ".join(str(данные.get("body_rendered") or "").split())
        print("   текст:   %s" % тело[:700])
    else:
        з = данные.get("headers") or {}
        if з.get("From"):
            print("   от:   %s" % з["From"])
        if з.get("Subject"):
            print("   тема: %s" % з["Subject"])
        т = " ".join(str(данные.get("snippet") or данные.get("tema") or "").split())
        if т:
            print("   текст: %s" % т[:700])

print("\n=== КАРТОЧКА В ЛЕНТЕ ===")
for р in c.execute("SELECT id, email, company_name, reply_kind, status, phone, "
                   "       substr(need,1,300) need FROM leads "
                   " WHERE email LIKE '%rostkran%'"):
    print("   #%s %s | %s | %s | тел %s"
          % (р["id"], р["email"], р["company_name"], р["reply_kind"], р["phone"]))
    print("   %s" % р["need"])
