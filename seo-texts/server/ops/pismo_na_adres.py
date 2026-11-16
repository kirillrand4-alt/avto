# -*- coding: utf-8 -*-
"""Последнее отправленное письмо на адрес: ящик, кампания, дата, тема, текст. Только чтение.   pismo_na_adres.py <email>"""
import sqlite3, sys
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
e = sys.argv[1].lower()
for м in c.execute("SELECT m.id, m.mailbox_id, m.campaign_id, m.sent_at, m.status, m.subject, m.body_rendered, r.inn, r.company_name FROM messages m "
                   "JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email)=? ORDER BY m.id DESC LIMIT 3", (e,)):
    print("m%s | %s | камп %s | %s | %s | ИНН %s %s" % (м[:5] + м[7:]))
    print("Тема:", м[5]); print(м[6] or "(нет body_rendered)"); print("-----")
нов = c.execute("SELECT COUNT(*) FROM recipients WHERE lower(email)=lower(?)", (sys.argv[2],)).fetchone()[0] if len(sys.argv) > 2 else None
if нов is not None: print("получатель с новым адресом уже есть:", нов)
