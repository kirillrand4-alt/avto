# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== по адресу из пересланного письма ===")
for а in ("phlebolog-ufa@mail.ru",):
    for r in c.execute("SELECT id, email, inn, company_name FROM recipients "
                       " WHERE email=?", (а,)):
        print("   %s -> rid %s | %s | ИНН %s" % (а, r["id"],
                                                 str(r["company_name"])[:40], r["inn"]))
print("")
print("=== кому писали с ящика k.yashin@kompressor-expert.ru 24-25.08 (Север) ===")
for r in c.execute(
        "SELECT m.id, m.sent_at, rc.id rid, rc.email, rc.company_name "
        "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE m.mailbox_id='k.yashin@kompressor-expert.ru' AND m.status='sent' "
        "   AND m.sent_at BETWEEN '2026-08-23' AND '2026-08-25T12:00' "
        "   AND (rc.company_name LIKE '%СЕВЕР%' OR rc.email LIKE '%sever%') "
        " ORDER BY m.sent_at DESC LIMIT 5"):
    print("   msg %s %s rid %s %-28s %s" % (r["id"], str(r["sent_at"])[:16],
                                            r["rid"], str(r["email"])[:28],
                                            str(r["company_name"])[:34]))
print("")
print("=== кому писали с v.prokhorov@compressor-air-expert.ru 24-25.08 (ТЭКО) ===")
for r in c.execute(
        "SELECT m.id, m.sent_at, rc.id rid, rc.email, rc.company_name "
        "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE m.mailbox_id='v.prokhorov@compressor-air-expert.ru' "
        "   AND m.status='sent' AND rc.company_name LIKE '%ТЭКО%' "
        " ORDER BY m.sent_at DESC LIMIT 5"):
    print("   msg %s %s rid %s %-28s %s" % (r["id"], str(r["sent_at"])[:16],
                                            r["rid"], str(r["email"])[:28],
                                            str(r["company_name"])[:34]))
c.close()
