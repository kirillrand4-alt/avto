# -*- coding: utf-8 -*-
"""Отказы «подозрение на спам» за сутки: время, ящик, кампания, адрес и
почтовик получателя; сколько ушло на тот же почтовик за то же время. Только чтение."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
мх = Counter()
for ts, mb, cid, em, mx, subj in c.execute(
        "SELECT e.event_ts, m.mailbox_id, m.campaign_id, r.email, r.mx_provider, "
        "(SELECT subject FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY id DESC LIMIT 1) "
        "FROM events e JOIN messages m ON m.id=e.message_id JOIN recipients r ON r.id=m.recipient_id "
        "WHERE e.event_type='reject_spam' AND e.event_ts>=strftime('%Y-%m-%dT%H:%M:%S','now','-1 day') ORDER BY e.event_ts"):
    мх[mx] += 1
    print("%s %-40s %-20s %-32s %-8s %s" % (ts[11:19], mb, str(кам.get(cid))[:20], em[:32], mx, str(subj)[:60]))
print("почтовик получателя:", dict(мх))
for mx, n in c.execute("SELECT r.mx_provider, COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                       "WHERE m.status='sent' AND m.sent_at>='2026-10-22' GROUP BY 1 ORDER BY 2 DESC LIMIT 6"):
    print("  ушло сегодня на %-10s %d" % (mx, n))
