# -*- coding: utf-8 -*-
"""Привязать карточку andryushchenko@chateaudetalu.ru к компании.

Письмо живое: «в какую стоимость данное оборудование? Возможно ли получить
КП» — заведующая лабораторией. Карточка завелась без ИНН, потому что ответ
пришёл вне переписки. Компанию ищем по домену отправителя среди тех, кому
мы писали, а не по названию из подписи.
"""
import json
import sqlite3
import sys

ДЕЛАТЬ = "primenit" in sys.argv[1:]
ДОМЕН = "chateaudetalu.ru"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

print("=== ПОЛУЧАТЕЛИ С ЭТОГО ДОМЕНА ===")
кандидаты = c.execute(
    "SELECT id, email, company_name, inn, region FROM recipients "
    " WHERE LOWER(email) LIKE ?", ("%@" + ДОМЕН,)).fetchall()
for р in кандидаты:
    print("   #%-7s %-34s %-34s ИНН %s | %s"
          % (р["id"], р["email"], str(р["company_name"] or "")[:34],
             р["inn"], р["region"]))

print("\n=== ЧТО МЫ ИМ ПИСАЛИ ===")
for р in c.execute(
        "SELECT m.id, m.sent_at, m.mailbox_id, m.subject, r.email "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE LOWER(r.email) LIKE ? ORDER BY m.sent_at DESC LIMIT 5",
        ("%@" + ДОМЕН,)):
    print("   письмо #%-6s %s с %s -> %s"
          % (р["id"], str(р["sent_at"])[:19], р["mailbox_id"], р["email"]))
    print("      тема: %s" % р["subject"])

карточка = c.execute("SELECT id, email, company_name, inn, recipient_id, version "
                     "  FROM leads WHERE LOWER(email)=?",
                     ("andryushchenko@" + ДОМЕН,)).fetchone()
print("\nкарточка: %s" % (dict(карточка) if карточка else "не найдена"))

if not ДЕЛАТЬ or not карточка or not кандидаты:
    print("\nвхолостую. Привязать — primenit")
    raise SystemExit(0)
ц = кандидаты[0]
c.execute("UPDATE leads SET recipient_id=?, company_name=?, inn=?, "
          "       version=version+1, updated_at=datetime('now') WHERE id=?",
          (ц["id"], ц["company_name"], ц["inn"], карточка["id"]))
c.commit()
for р in c.execute("SELECT id, email, company_name, inn, recipient_id FROM leads "
                   " WHERE id=?", (карточка["id"],)):
    print("стало: %s" % dict(р))
