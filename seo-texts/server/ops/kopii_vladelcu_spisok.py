# -*- coding: utf-8 -*-
"""Какие письма уходили на ящики владельца (копии): ящик, дата, тема."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for r in c.execute("""SELECT m.id, r.email, m.mailbox_id, substr(m.sent_at,1,16), m.subject, m.campaign_id
   FROM messages m JOIN recipients r ON r.id=m.recipient_id
   WHERE m.status='sent' AND (r.email LIKE '%prokompressor.ru' OR r.email LIKE 'kirillrand%' OR r.source LIKE '%kopi%' OR r.source LIKE '%vladel%')
   ORDER BY m.sent_at DESC LIMIT 40"""):
    print(r)
