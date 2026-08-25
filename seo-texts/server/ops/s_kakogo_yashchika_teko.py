# -*- coding: utf-8 -*-
"""С какого ящика ушло письмо в «ТЭКО» и куда пришёл ответ.

В прошлом ответе я назвал ящик, КУДА пришёл ответ, как отправителя — это
разные поля: у события mailbox_id это наш ящик-получатель, у письма
mailbox_id это ящик-отправитель. Смотрим оба и не путаем.
"""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("=== ПИСЬМА В ООО «ТЭКО» (ИНН 4703137447) ===")
for р in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.mailbox_id, m.subject, "
        "       m.rfc_message_id, r.email FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE r.inn='4703137447' ORDER BY m.sent_at DESC"):
    print("   письмо #%s %s %s" % (р["id"], р["status"], str(р["sent_at"])[:19]))
    print("      С ЯЩИКА: %s" % р["mailbox_id"])
    print("      кому:    %s" % р["email"])
    print("      тема:    %s" % р["subject"])
    print("      msg-id:  %s" % str(р["rfc_message_id"])[:70])

р = c.execute("SELECT id, event_ts, mailbox_id, detail_json FROM events "
              " WHERE id=183709").fetchone()
d = json.loads(р["detail_json"] or "{}")
print("\n=== ОТВЕТ ===")
print("   пришёл В ЯЩИК: %s" % (d.get("inbox_mailbox") or р["mailbox_id"]))
print("   от:            %s" % ((d.get("headers") or {}).get("From")))
print("   когда:         %s" % р["event_ts"])
