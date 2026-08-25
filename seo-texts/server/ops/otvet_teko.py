# -*- coding: utf-8 -*-
"""Ответ «ТЭКО» (Сергей Голышев, gmail) — дошёл ли он до ленты лидов."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("=== СОБЫТИЯ С ЭТИМ АДРЕСОМ ИЛИ ТЕКСТОМ ===")
for р in c.execute(
        "SELECT id, event_ts, event_type, recipient_id, mailbox_id, detail_json "
        "  FROM events "
        " WHERE detail_json LIKE '%s9213674759%' "
        "    OR detail_json LIKE '%не актуален, мы их продаём%' "
        " ORDER BY id DESC LIMIT 5"):
    d = json.loads(р["detail_json"] or "{}")
    з = d.get("headers") or {}
    print("   #%-7s %s %-10s получатель %-7s ящик %s"
          % (р["id"], str(р["event_ts"])[:19], р["event_type"],
             р["recipient_id"] or "НЕТ", р["mailbox_id"]))
    print("      от:    %s" % з.get("From"))
    print("      тема:  %s" % з.get("Subject"))
    print("      метка: %s" % d.get("reply_kind"))
    print("      текст: %s" % " ".join(str(d.get("snippet") or "").split())[:160])

print("\n=== КАРТОЧКА В ЛЕНТЕ ===")
нашли = False
for р in c.execute(
        "SELECT id, email, company_name, inn, reply_kind, status, created_at, "
        "       substr(need,1,80) need FROM leads "
        " WHERE email LIKE '%s9213674759%' OR company_name LIKE '%ТЭКО%' "
        "    OR need LIKE '%мы их продаём%'"):
    нашли = True
    print("   #%s %s | %s | %s | %s | %s"
          % (р["id"], р["email"], р["company_name"], р["reply_kind"],
             р["status"], str(р["created_at"])[:19]))
    print("      %s" % р["need"])
if not нашли:
    print("   карточки нет")

print("\n=== КОМУ МЫ ПИСАЛИ В ЭТУ КОМПАНИЮ ===")
for р in c.execute(
        "SELECT m.id, m.sent_at, m.mailbox_id, m.subject, r.email, "
        "       r.company_name, r.inn FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE r.company_name LIKE '%ТЭКО%' ORDER BY m.sent_at DESC LIMIT 5"):
    print("   письмо #%-6s %s -> %-28s %-24s %s"
          % (р["id"], str(р["sent_at"])[:16], str(р["email"])[:28],
             str(р["company_name"])[:24], str(р["subject"])[:40]))
