# -*- coding: utf-8 -*-
"""Письма и карточки на адреса домена: pisma_na_domen.py <домен>. Только чтение."""
import sqlite3, sys
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
д = "%@" + sys.argv[1].lower()
for r in к.execute("SELECT m.id, lower(r.email), m.status, m.sent_at, m.campaign_id, m.mailbox_id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email) LIKE ? ORDER BY m.id", (д,)):
    print("письмо", r)
for r in к.execute("SELECT id, email, status, campaign_id, subject FROM confirm_reviews WHERE lower(email) LIKE ? ORDER BY id", (д,)):
    print("карточка", r)
