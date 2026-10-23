# -*- coding: utf-8 -*-
"""Писали ли мы на адреса (и их домены): письма, ручные ответы/карточки. Только чтение.
    pisali_li.py адрес1,адрес2,..."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for а in sys.argv[1].lower().split(","):
    д = "@" + а.split("@")[1]
    п = c.execute("SELECT m.id, m.status, substr(coalesce(m.sent_at,''),1,16), m.mailbox_id FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                  "WHERE lower(r.email)=? ORDER BY m.id", (а,)).fetchall()
    к = c.execute("SELECT id, kind, status, substr(created_at,1,16) FROM confirm_reviews WHERE lower(email)=? ORDER BY id", (а,)).fetchall()
    пд = [] if д in ("@gmail.com", "@mail.ru", "@yandex.ru", "@bk.ru", "@list.ru", "@inbox.ru", "@rambler.ru") else c.execute("SELECT lower(r.email), m.status, substr(coalesce(m.sent_at,''),1,10) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE lower(r.email) LIKE ? AND m.status='sent' ORDER BY m.id", ("%" + д,)).fetchall()
    print("\n%s\n  письма на адрес: %s\n  карточки: %s\n  отправлено на домен %s: %s" % (а, п or "нет", к or "нет", д, пд or "нет"))
