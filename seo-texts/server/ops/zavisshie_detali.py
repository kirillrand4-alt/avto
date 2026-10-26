# -*- coding: utf-8 -*-
"""Письма в 'sending': кому, ящик, кампания, когда взяты. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for r in c.execute("SELECT m.id, m.campaign_id, m.claimed_at, m.mailbox_id, r.email, r.inn, r.domain, length(m.body_rendered) "
                   "FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sending' ORDER BY m.claimed_at"):
    print(r)
