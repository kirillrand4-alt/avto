# -*- coding: utf-8 -*-
"""Что ушло сегодня и какие старые письма стоят в расписании с прошедшим сроком."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("--- ушло сегодня ---")
for р in c.execute("SELECT m.id, m.campaign_id, m.mailbox_id, m.sent_at, m.subject, r.email "
                   "FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE m.status='sent' AND m.sent_at >= date('now')"):
    print("   m%s камп %s | %s -> %s | %s | %s" % (р["id"], р["campaign_id"], р["mailbox_id"],
          р["email"], р["sent_at"][:19], str(р["subject"])[:60]))
print("--- в расписании со сроком раньше 13.10 06:00 UTC ---")
for р in c.execute("SELECT m.id, m.campaign_id, m.status, m.scheduled_at, m.mailbox_id, r.email, "
                   "m.created_at FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE m.status IN ('scheduled','sending') AND m.scheduled_at < '2026-10-13T06'"):
    print("   m%s камп %s %s срок %s ящ=%s -> %s (создано %s)" % (р["id"], р["campaign_id"], р["status"],
          str(р["scheduled_at"])[:16], р["mailbox_id"], р["email"], str(р["created_at"])[:10]))
print("=== КТО УШЁЛ ===")
