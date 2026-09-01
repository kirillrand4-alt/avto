# -*- coding: utf-8 -*-
"""Только чтение: что прилетело в ответ на 90 писем с food-sort.ru."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("=== ВСЕ события food-sort.ru ===")
for р in s.execute("SELECT id, event_type, created_at, mailbox_id FROM events"
                   " WHERE mailbox_id LIKE '%food-sort%' ORDER BY id"):
    print("  #%-8s %-14s %s" % (р["id"], р["event_type"], str(р["created_at"])[:19]))

print("\n=== ДЛЯ СРАВНЕНИЯ: доля отбивок по meyer-ящикам за 2 суток ===")
c = Counter()
for р in s.execute("SELECT mailbox_id, event_type FROM events"
                   " WHERE created_at >= datetime('now','-2 day')"
                   " AND event_type IN ('sent','bounce','reject_spam')"):
    c[(str(р["mailbox_id"]), str(р["event_type"]))] += 1
ящики = sorted({m for m, _ in c})
print("  %-40s %6s %8s %10s" % ("ящик", "sent", "bounce", "reject_spam"))
for m in ящики:
    se, bo, rs = c.get((m, "sent"), 0), c.get((m, "bounce"), 0), c.get((m, "reject_spam"), 0)
    if se or bo or rs:
        print("  %-40s %6d %8d %10d" % (m[:40], se, bo, rs))

print("\n=== ИТОГ ===")
n90 = s.execute("SELECT COUNT(*) n FROM messages WHERE mailbox_id='a.erokhin@food-sort.ru'"
                " AND status='sent'").fetchone()["n"]
bo = s.execute("SELECT COUNT(*) n FROM events WHERE mailbox_id LIKE '%food-sort%'"
               " AND event_type='bounce'").fetchone()["n"]
rs = s.execute("SELECT COUNT(*) n FROM events WHERE mailbox_id LIKE '%food-sort%'"
               " AND event_type='reject_spam'").fetchone()["n"]
print("  отправлено с food-sort.ru: %d" % n90)
print("  жёстких отбивок: %d (%.1f%%)" % (bo, 100.0 * bo / max(1, n90)))
print("  отказов «подозрение на спам»: %d (%.1f%%)" % (rs, 100.0 * rs / max(1, n90)))
print("  событий sent по этому ящику: %d — их нет, поэтому круг ротации не двигался"
      % s.execute("SELECT COUNT(*) n FROM events WHERE mailbox_id LIKE '%food-sort%'"
                  " AND event_type='sent'").fetchone()["n"])
