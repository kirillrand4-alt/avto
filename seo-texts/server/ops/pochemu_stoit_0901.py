# -*- coding: utf-8 -*-
"""Только чтение: почему очередь не уходит при открытом окне."""
import glob
import io
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ВРЕМЯ ===")
print("  сервер локально: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("  SQLite now (UTC): %s" % s.execute("SELECT datetime('now') n").fetchone()["n"])

print("\n=== СОЗРЕЛО ЛИ ===")
a = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
              " AND scheduled_at <= datetime('now')").fetchone()["n"]
print("  scheduled со временем <= сейчас (UTC): %d" % a)
for р in s.execute("SELECT substr(scheduled_at,1,13) ч, COUNT(*) n FROM messages"
                   " WHERE status='scheduled' GROUP BY ч ORDER BY ч"):
    print("     %s -> %d" % (р["ч"], р["n"]))

print("\n=== ПОСЛЕДНЯЯ АКТИВНОСТЬ ===")
п = s.execute("SELECT MAX(created_at) m FROM events WHERE event_type='sent'").fetchone()
print("  последнее событие sent: %s" % п["m"])
print("  событий sent за час   : %d"
      % s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                  " AND created_at >= datetime('now','-1 hour')").fetchone()["n"])
print("  писем в статусе sending: %d"
      % s.execute("SELECT COUNT(*) n FROM messages WHERE status='sending'").fetchone()["n"])

print("\n=== СЛУЖБА И ЕЁ ПРОЦЕСС ===")
try:
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-Service SenderPanel | Select Status; "
                        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                        "Where-Object {$_.CommandLine -like '*panel*' -or "
                        "$_.CommandLine -like '*orchestr*' -or $_.CommandLine -like '*serve*'} | "
                        "Select ProcessId,CreationDate | Format-List"],
                       capture_output=True, text=True, timeout=70)
    print("  " + (r.stdout.strip()[:700] or "?"))
except Exception as ex:
    print("  ", str(ex)[:90])

print("\n=== ЛОГ ПАНЕЛИ: ХВОСТ ===")
логи = []
for шаб in (r"C:\sender\*.log", r"C:\sender\logs\*.log", r"C:\sender\sender\*.log"):
    логи += glob.glob(шаб)
логи = sorted(логи, key=os.path.getmtime, reverse=True)[:3]
for л in логи:
    т = datetime.fromtimestamp(os.path.getmtime(л))
    print("\n  --- %s (изменён %s) ---" % (os.path.basename(л), т.strftime("%H:%M:%S")))
    try:
        стр = io.open(л, encoding="utf-8", errors="replace").read().splitlines()
        for x in стр[-14:]:
            print("     " + x[:118])
    except Exception as ex:
        print("     ", str(ex)[:80])

print("\n=== ИТОГ ===")
print("  если созревших много, а событий sent за час ноль — тик оркестратора не идёт")
