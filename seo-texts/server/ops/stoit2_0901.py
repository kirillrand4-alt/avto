# -*- coding: utf-8 -*-
"""Только чтение: главное печатаем ПОСЛЕДНИМ."""
import sqlite3
import subprocess
from datetime import datetime

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ПРОЦЕССЫ ПАНЕЛИ ===")
try:
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                        "Select-Object ProcessId,CreationDate,"
                        "@{n='cmd';e={$_.CommandLine.Substring(0,[Math]::Min(70,$_.CommandLine.Length))}} | "
                        "Format-Table -AutoSize | Out-String -Width 200"],
                       capture_output=True, text=True, timeout=70)
    print(r.stdout[:1400])
except Exception as ex:
    print("  ", str(ex)[:90])

print("\n=== СОБЫТИЯ sent ПО 10 МИНУТ, последний час ===")
for р in s.execute("SELECT substr(created_at,1,15) м, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= datetime('now','-2 hour')"
                   " GROUP BY м ORDER BY м DESC LIMIT 12"):
    print("  %s0  %d" % (р["м"], р["n"]))

print("\n=== ИТОГ ===")
print("  сервер локально : %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("  SQLite now (UTC): %s" % s.execute("SELECT datetime('now') n").fetchone()["n"])
a = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
              " AND scheduled_at <= datetime('now')").fetchone()["n"]
вс = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
print("  scheduled всего: %d, из них СОЗРЕЛО: %d" % (вс, a))
print("  в статусе sending: %d"
      % s.execute("SELECT COUNT(*) n FROM messages WHERE status='sending'").fetchone()["n"])
print("  последнее событие sent: %s"
      % s.execute("SELECT MAX(created_at) m FROM events WHERE event_type='sent'").fetchone()["m"])
print("  событий sent за последний час: %d"
      % s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                  " AND created_at >= datetime('now','-1 hour')").fetchone()["n"])
print("  ближайшее время в очереди: %s"
      % s.execute("SELECT MIN(scheduled_at) m FROM messages WHERE status='scheduled'"
                  ).fetchone()["m"])
