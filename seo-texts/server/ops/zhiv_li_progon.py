# -*- coding: utf-8 -*-
"""Жив ли отцеплённый прогон: процессы, свежесть логов, счёт написанного."""
import io
import json
import os
import subprocess
import time

КАТАЛОГ = r"C:\sender\_ops"
сейчас = time.time()

print("=== ПРОЦЕССЫ PYTHON ===")
try:
    в = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
         "Select-Object ProcessId,CreationDate,"
         "@{n='cmd';e={$_.CommandLine.Substring(0,[Math]::Min(150,"
         "$_.CommandLine.Length))}} | Format-List"],
        capture_output=True, timeout=60)
    т = (в.stdout or b"").decode("cp866", "replace")
    for с in т.splitlines():
        if с.strip():
            print("   %s" % с.strip()[:150])
except Exception as e:  # noqa: BLE001
    print("   не вышло: %s" % str(e)[:80])

print("\n=== СВЕЖЕСТЬ ФАЙЛОВ ПРОГОНА ===")
for имя in ("ochered-25-08.jsonl", "ochered2508-blok1-meyer.log",
            "gen-partiya-935.jsonl", "gen-partiya-935-vyzovy.jsonl"):
    п = os.path.join(КАТАЛОГ, имя)
    if not os.path.exists(п):
        print("   %-34s нет файла" % имя)
        continue
    прошло = (сейчас - os.path.getmtime(п)) / 60.0
    print("   %-34s %9d б, обновлён %.1f мин назад"
          % (имя, os.path.getsize(п), прошло))

лог = os.path.join(КАТАЛОГ, "ochered2508-blok1-meyer.log")
if os.path.exists(лог):
    строки = io.open(лог, encoding="utf-8", errors="replace").read().splitlines()
    print("\n=== ХВОСТ ЛОГА БЛОКА (%d строк) ===" % len(строки))
    for с in строки[-16:]:
        print("   %s" % с[:150])

# Сколько писем этот прогон уже положил в очередь подтверждения.
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
n = c.execute("SELECT COUNT(*) FROM confirm_reviews "
              " WHERE created_at >= '2026-08-25 10:35'").fetchone()[0]
print("\nкарточек создано после старта прогона: %d" % n)
