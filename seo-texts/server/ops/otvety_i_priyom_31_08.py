# -*- coding: utf-8 -*-
"""Только чтение: приходят ли ответы и жив ли приёмник почты."""
import sqlite3
from collections import Counter
from datetime import datetime

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("=== ТИПЫ СОБЫТИЙ ЗА 3 СУТОК ===")
for р in s.execute("SELECT event_type, COUNT(*) n, MAX(created_at) посл FROM events"
                   " WHERE created_at >= datetime('now','-3 day')"
                   " GROUP BY event_type ORDER BY n DESC"):
    print("  %-18s %5d   последнее %s" % (р["event_type"], р["n"], str(р["посл"])[:19]))

print("\n=== ВСЕ СОБЫТИЯ-ОТВЕТЫ ПО ДНЯМ (7 дней) ===")
for р in s.execute("SELECT substr(created_at,1,10) д, event_type, COUNT(*) n FROM events"
                   " WHERE event_type LIKE '%repl%' OR event_type LIKE '%otvet%'"
                   " OR event_type LIKE '%answer%' OR event_type='response'"
                   " GROUP BY д, event_type ORDER BY д DESC LIMIT 14"):
    print("  %s  %-16s %d" % (р["д"], р["event_type"], р["n"]))

print("\n=== ПОСЛЕДНИЕ 10 СОБЫТИЙ ЛЮБОГО ВХОДЯЩЕГО ТИПА ===")
for р in s.execute("SELECT id, event_type, created_at, mailbox_id FROM events"
                   " WHERE event_type NOT IN ('sent','reply_sent')"
                   " ORDER BY id DESC LIMIT 10"):
    print("  #%-8s %-16s %s  %s" % (р["id"], р["event_type"],
                                    str(р["created_at"])[:19],
                                    str(р["mailbox_id"] or "")[:32]))

print("\n=== ЛИДЫ / ОТВЕТЫ В ОТДЕЛЬНЫХ ТАБЛИЦАХ ===")
for т in ("leads", "lead_events"):
    try:
        n = s.execute("SELECT COUNT(*) n FROM %s" % т).fetchone()["n"]
        посл = s.execute("SELECT MAX(created_at) m FROM %s" % т).fetchone()["m"]
        сег = s.execute("SELECT COUNT(*) n FROM %s WHERE created_at >= date('now')" % т
                        ).fetchone()["n"]
        print("  %-14s всего %5d | сегодня %3d | последняя %s" % (т, n, сег, str(посл)[:19]))
    except Exception as ex:
        print("  %-14s %s" % (т, str(ex)[:60]))

print("\n=== ОЧЕРЕДЬ ОТВЕТОВ В confirm_reviews (kind=reply) ===")
for р in s.execute("SELECT status, COUNT(*) n, MAX(created_at) m FROM confirm_reviews"
                   " WHERE kind='reply' GROUP BY status ORDER BY n DESC"):
    print("  %-14s %4d  последняя %s" % (р["status"], р["n"], str(р["m"])[:19]))

print("\n=== ИТОГ ===")
print("  сейчас: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
