# -*- coding: utf-8 -*-
"""Только чтение: кто на самом деле отправляет и возьмёт ли кампанию 11."""
import io
import re
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== СЕЙЧАС ===")
print("  время сервера: %s" % datetime.now().strftime("%H:%M:%S"))
print("  UTC в базе   : %s" % s.execute("SELECT datetime('now') n").fetchone()["n"])

print("\n=== ОТПРАВЛЕНО ЗА ПОСЛЕДНИЕ 3 ЧАСА ===")
for р in s.execute("SELECT substr(created_at,1,16) м, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= datetime('now','-3 hour')"
                   " GROUP BY м ORDER BY м DESC LIMIT 15"):
    print("  %s  %d" % (р["м"], р["n"]))
итог = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                 " AND created_at >= datetime('now','-3 hour')").fetchone()["n"]
print("  всего за 3 часа: %d" % итог)

print("\n=== ОЧЕРЕДЬ СЕЙЧАС ===")
for р in s.execute("SELECT status, COUNT(*) n FROM messages"
                   " WHERE status IN ('scheduled','sending') GROUP BY status"):
    print("  %-12s %d" % (р["status"], р["n"]))
for р in s.execute("SELECT substr(scheduled_at,1,13) ч, COUNT(*) n FROM messages"
                   " WHERE status='scheduled' GROUP BY ч ORDER BY ч"):
    print("     %s -> %d" % (р["ч"], р["n"]))

print("\n=== active_campaigns: КАК ЕГО ЧИТАЕТ ОРКЕСТРАТОР ===")
print("  значение в конфиге: %r" % (cfg.get("orchestrator.active_campaigns"),))
стр = io.open(r"C:\sender\sender\orchestrator.py", encoding="utf-8",
              errors="replace").read().splitlines()
for i, x in enumerate(стр):
    if "active_campaigns" in x:
        print("  --- orchestrator.py:%d ---" % (i + 1))
        for j in range(max(0, i - 6), min(i + 12, len(стр))):
            print("     %4d  %s" % (j + 1, стр[j][:104]))
        break

print("\n=== ИТОГ: КАКИЕ КАМПАНИИ УХОДИЛИ СЕГОДНЯ ===")
for р in s.execute("SELECT m.campaign_id k, COUNT(*) n FROM events e"
                   " JOIN messages m ON m.id=e.message_id"
                   " WHERE e.event_type='sent' AND e.created_at >= datetime('now','-24 hour')"
                   " GROUP BY k"):
    print("  кампания %-4s %d писем" % (р["k"], р["n"]))
