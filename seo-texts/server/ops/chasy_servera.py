# -*- coding: utf-8 -*-
"""Сверка часов: системное время, UTC, что пишет база и что показывает лента.

Гистограмма отправок дала 00-03 «UTC», а лента панели на том же материале
показывает 09:54-10:15. Разница в семь часов — это либо часы машины, либо
разные зоны у sent_at и event_ts. Пока не сведём, разговор про слоты слеп.
"""
import sqlite3
import time
from datetime import datetime, timezone

print("time.tzname      %s" % (time.tzname,))
print("datetime.now()   %s" % datetime.now().isoformat(timespec="seconds"))
print("now(utc)         %s" % datetime.now(timezone.utc).isoformat(timespec="seconds"))

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("sqlite datetime('now') %s" % c.execute("SELECT datetime('now')").fetchone()[0])
print("sqlite localtime       %s"
      % c.execute("SELECT datetime('now','localtime')").fetchone()[0])

print("\n=== ПОСЛЕДНИЕ ОТПРАВЛЕННЫЕ ===")
for р in c.execute("SELECT id, sent_at, scheduled_at, created_at, mailbox_id "
                   "  FROM messages WHERE status='sent' "
                   " ORDER BY sent_at DESC LIMIT 5"):
    print("   #%-7s ушло %s | слот %s | ящик %s"
          % (р["id"], р["sent_at"], р["scheduled_at"], р["mailbox_id"]))

print("\n=== ПОСЛЕДНИЕ СОБЫТИЯ ЛЕНТЫ ===")
for р in c.execute("SELECT id, event_type, event_ts, created_at, mailbox_id "
                   "  FROM events ORDER BY id DESC LIMIT 6"):
    print("   #%-7s %-12s ts %s | created %s | %s"
          % (р["id"], р["event_type"], р["event_ts"], р["created_at"],
             р["mailbox_id"] or "-"))
