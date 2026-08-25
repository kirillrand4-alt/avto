# -*- coding: utf-8 -*-
"""На какой адрес ушло письмо, ответ на которое пришёл с чужой почты.

Тема ответа — «Re: Fwd: Вопрос по компрессорному парку для «Север»»: письмо
переслали внутри компании, и отвечал уже снабженец со своего ящика. Ищем
исходное письмо по теме и ящику отправителя.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("=== ИСХОДНОЕ ПИСЬМО ===")
for р in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.mailbox_id, m.subject, "
        "       r.id rid, r.email, r.company_name, r.inn "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.subject LIKE '%компрессорному парку для%Север%' "
        " ORDER BY m.sent_at DESC LIMIT 5"):
    print("   письмо #%s %s %s" % (р["id"], р["status"], str(р["sent_at"])[:19]))
    print("      с ящика:  %s" % р["mailbox_id"])
    print("      кому:     %s" % р["email"])
    print("      компания: %s (ИНН %s, получатель #%s)"
          % (р["company_name"], р["inn"], р["rid"]))
    print("      тема:     %s" % р["subject"])

print("\n=== ЧТО ЕЩЁ ЗНАЕМ ПРО ЭТУ КОМПАНИЮ ===")
for р in c.execute(
        "SELECT id, email, company_name, inn FROM recipients "
        " WHERE company_name LIKE '%СЕВЕР%' AND inn IN ("
        "   SELECT inn FROM recipients WHERE company_name LIKE '%СЕВЕР%') "
        " LIMIT 8"):
    print("   #%-6s %-32s %-34s %s" % (р["id"], р["email"],
                                       str(р["company_name"])[:34], р["inn"]))
