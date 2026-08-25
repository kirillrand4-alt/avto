# -*- coding: utf-8 -*-
"""Идёт ли отправка сейчас и кто держит базу."""
import os
import sqlite3
import subprocess
import time

c = sqlite3.connect(r"C:\sender\sender.db", timeout=5)
c.row_factory = sqlite3.Row
print("=== ОТПРАВКА ЗА ПОСЛЕДНИЙ ЧАС ПО ПЯТНАДЦАТИМИНУТКАМ ===")
for р in c.execute(
        "SELECT substr(sent_at,1,15) т, COUNT(*) n FROM messages "
        " WHERE status='sent' AND sent_at >= datetime('now','-3 hours') "
        " GROUP BY т ORDER BY т"):
    print("  %s0  %s %d" % (р["т"], "#" * min(40, р["n"]), р["n"]))

print("\n=== РЕЖИМ ЖУРНАЛА БАЗЫ ===")
print("  journal_mode = %s" % c.execute("PRAGMA journal_mode").fetchone()[0])
print("  busy_timeout = %s" % c.execute("PRAGMA busy_timeout").fetchone()[0])
for ф in ("sender.db-wal", "sender.db-shm", "sender.db-journal"):
    п = r"C:\sender\%s" % ф
    if os.path.exists(п):
        print("  %s: %.1f МБ" % (ф, os.path.getsize(п) / 1048576.0))

print("\n=== ПРОЦЕССЫ, ДЕРЖАЩИЕ sender.db ===")
из = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Csv "
     "-NoTypeInformation"],
    capture_output=True, text=True, timeout=120).stdout
for с in из.splitlines()[1:]:
    if "python" in с.lower():
        print("  " + с.strip()[:180])

print("\n=== ПРОБА ЗАПИСИ (то, что делает автоотправка) ===")
try:
    т0 = time.time()
    c2 = sqlite3.connect(r"C:\sender\sender.db", timeout=10)
    c2.execute("BEGIN IMMEDIATE")
    c2.execute("ROLLBACK")
    print("  BEGIN IMMEDIATE прошёл за %.2f с — база СВОБОДНА" % (time.time() - т0))
except Exception as e:  # noqa: BLE001
    print("  БАЗА ЗАНЯТА: %s" % str(e)[:120])
