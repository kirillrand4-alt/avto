# -*- coding: utf-8 -*-
"""Только чтение: в каком времени лежит scheduled_at и что сейчас созрело."""
import sqlite3
from datetime import datetime, timezone

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("=== ОБРАЗЦЫ scheduled_at ===")
for р in s.execute("SELECT id, scheduled_at FROM messages WHERE status='scheduled'"
                   " ORDER BY scheduled_at DESC LIMIT 5"):
    print("  #%-7s %s" % (р["id"], р["scheduled_at"]))
for р in s.execute("SELECT id, scheduled_at FROM messages WHERE status='scheduled'"
                   " ORDER BY scheduled_at ASC LIMIT 3"):
    print("  #%-7s %s  (самое раннее)" % (р["id"], р["scheduled_at"]))

print("\n=== ЧАСЫ ===")
print("  datetime('now') в SQLite (UTC): %s"
      % s.execute("SELECT datetime('now') n").fetchone()["n"])
print("  локальное время сервера       : %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("  UTC сейчас                    : %s"
      % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

print("\n=== СОЗРЕЛО ПО РАЗНЫМ ТРАКТОВКАМ ===")
a = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
              " AND scheduled_at <= datetime('now')").fetchone()["n"]
b = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
              " AND scheduled_at <= datetime('now','+3 hour')").fetchone()["n"]
print("  scheduled_at <= UTC сейчас        : %d" % a)
print("  scheduled_at <= UTC+3 (мск сейчас): %d" % b)

print("\n=== КОМУ УХОДИЛО В ПОСЛЕДНИЙ ЧАС АКТИВНОСТИ (04:00 UTC) ===")
for р in s.execute(
        "SELECT r.tz, r.region, COUNT(*) n FROM events e"
        " JOIN messages m ON m.id=e.message_id JOIN recipients r ON r.id=m.recipient_id"
        " WHERE e.event_type='sent' AND e.created_at >= '2026-09-01T04'"
        " GROUP BY r.tz, r.region ORDER BY n DESC LIMIT 10"):
    print("  %-22s %-28s %d" % (str(р["tz"] or "(пусто)"), str(р["region"])[:28], р["n"]))

print("\n=== ИТОГ ===")
print("  окно 09:00-14:00 по поясу ПОЛУЧАТЕЛЯ (by_recipient_tz=True)")
print("  сейчас мск %s" % datetime.now().strftime("%H:%M"))
print("  для москвичей окно откроется в 09:00 мск, это через %d мин"
      % max(0, (9 * 60) - (datetime.now().hour * 60 + datetime.now().minute)))
