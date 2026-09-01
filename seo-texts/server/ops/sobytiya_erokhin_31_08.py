# -*- coding: utf-8 -*-
"""Только чтение: почему указатель ротации застрял на i.boyarkin."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== events: последние 12 с непустым mailbox_id ===")
for р in s.execute("SELECT id, event_type, mailbox_id, created_at FROM events"
                   " WHERE COALESCE(mailbox_id,'')<>'' ORDER BY id DESC LIMIT 12"):
    print("  #%-8s %-12s %-36s %s"
          % (р["id"], р["event_type"], str(р["mailbox_id"])[:36], str(р["created_at"])[:19]))

print("\n=== есть ли ХОТЬ ОДНО событие с a.erokhin ===")
n = s.execute("SELECT COUNT(*) n FROM events WHERE mailbox_id LIKE '%food-sort%'"
              ).fetchone()["n"]
print("  событий с food-sort: %d" % n)

print("\n=== события типа sent за последние сутки: по ящикам ===")
c = Counter()
for р in s.execute("SELECT mailbox_id, event_type FROM events"
                   " WHERE event_type IN ('sent','reply_sent')"
                   " AND created_at >= datetime('now','-2 day')"):
    c[str(р["mailbox_id"])] += 1
for k, v in c.most_common(12):
    print("  %-40s %d" % (k[:40], v))

print("\n=== для сравнения: messages.status='sent' за те же сутки ===")
c2 = Counter()
for р in s.execute("SELECT mailbox_id FROM messages WHERE status='sent'"
                   " AND sent_at >= datetime('now','-2 day')"):
    c2[str(р["mailbox_id"])] += 1
for k, v in c2.most_common(12):
    print("  %-40s %d" % (k[:40], v))

print("\n=== ИТОГ ===")
пусто = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                  " AND COALESCE(mailbox_id,'')=''").fetchone()["n"]
всего = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'").fetchone()["n"]
print("  событий sent всего: %d, из них БЕЗ mailbox_id: %d" % (всего, пусто))
print("  указатель ротации читает только события с непустым mailbox_id,")
print("  поэтому отправки без него круг не двигают")
