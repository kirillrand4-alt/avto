# -*- coding: utf-8 -*-
"""Только чтение: поминутное расписание очереди и темп отправки."""
import sqlite3
from datetime import datetime

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
now = s.execute("SELECT datetime('now') n").fetchone()["n"]

print("=== ОЧЕРЕДЬ ПО 10 МИНУТ (UTC / мск) ===")
for р in s.execute("SELECT substr(scheduled_at,1,15) м, COUNT(*) n FROM messages"
                   " WHERE status='scheduled' AND scheduled_at >= '2026-09-01'"
                   " GROUP BY м ORDER BY м LIMIT 24"):
    м = р["м"]
    try:
        d = datetime.strptime(м + "0", "%Y-%m-%dT%H:%M")
        мск = "%02d:%02d мск" % ((d.hour + 3) % 24, d.minute)
    except Exception:
        мск = ""
    метка = "  <- уже созрело" if м + "0" <= now.replace(" ", "T") else ""
    print("  %s0  %4d  = %s%s" % (м, р["n"], мск, метка))

print("\n=== ТЕМП ОТПРАВКИ ПО 10 МИНУТ (события sent) ===")
for р in s.execute("SELECT substr(created_at,1,15) м, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= datetime('now','-90 minute')"
                   " GROUP BY м ORDER BY м"):
    print("  %s0  %d" % (р["м"], р["n"]))

print("\n=== ИТОГ ===")
print("  сейчас UTC %s (мск %s)" % (now, datetime.now().strftime("%H:%M:%S")))
вс = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
буд = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
                " AND scheduled_at > datetime('now')").fetchone()["n"]
посл = s.execute("SELECT MAX(scheduled_at) m FROM messages WHERE status='scheduled'"
                 ).fetchone()["m"]
за_час = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                   " AND created_at >= datetime('now','-1 hour')").fetchone()["n"]
print("  в очереди %d, из них на будущее %d" % (вс, буд))
print("  последнее назначенное время: %s" % посл)
print("  отправлено за последний час: %d" % за_час)
if за_час:
    print("  при таком темпе остаток уйдёт примерно за %.1f ч" % (вс / float(за_час)))
