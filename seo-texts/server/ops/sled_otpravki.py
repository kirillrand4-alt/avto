# -*- coding: utf-8 -*-
"""След отправки карточки: статус, время, события reply_sent и строка messages: sled_otpravki.py ID"""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
к = int(sys.argv[1])
print(c.execute("SELECT id, status, decided_at, email, subject FROM confirm_reviews WHERE id=?", (к,)).fetchone())
ec = [r[1] for r in c.execute("PRAGMA table_info(events)")]
for r in c.execute("SELECT event_type, event_ts, mailbox_id, substr(detail_json,1,300) FROM events WHERE event_type LIKE 'reply_sent%' ORDER BY id DESC LIMIT 5"):
    print("событие", r)
for r in c.execute("SELECT m.id, m.status, m.sent_at, m.mailbox_id, m.subject FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email)=?", ("chmz@molsib.com",)):
    print("письмо", r)
