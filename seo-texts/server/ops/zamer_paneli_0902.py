# -*- coding: utf-8 -*-
"""Только чтение: замеряем сам API панели и состояние WAL."""
import sqlite3
import subprocess
import time
import urllib.request

print("=== ОТКЛИК API ПАНЕЛИ ===")
for путь in ("/api/health", "/api/confirm/counts", "/api/confirm?status=pending&limit=50"):
    t = time.time()
    try:
        with urllib.request.urlopen("http://127.0.0.1:8091" + путь, timeout=60) as r:
            тело = r.read()
        print("  %-42s %5.2f с  %d Б  код %s"
              % (путь, time.time() - t, len(тело), r.status))
    except Exception as ex:
        print("  %-42s %5.2f с  %s" % (путь, time.time() - t, str(ex)[:60]))

print("\n=== WAL ===")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
try:
    print("  journal_mode: %s" % c.execute("PRAGMA journal_mode").fetchone()[0])
    print("  wal_autocheckpoint: %s" % c.execute("PRAGMA wal_autocheckpoint").fetchone()[0])
    print("  страниц в WAL: %s" % (c.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone(),))
except Exception as ex:
    print("  %s" % str(ex)[:120])

print("\n=== ЗАГРУЗКА МАШИНЫ ===")
out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "$c=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage"
     " -Average).Average; $m=Get-CimInstance Win32_OperatingSystem;"
     " \"CPU $c%; память свободно $([math]::Round($m.FreePhysicalMemory/1024))"
     " МБ из $([math]::Round($m.TotalVisibleMemorySize/1024)) МБ\""],
    capture_output=True, text=True, timeout=60)
print("  %s" % out.stdout.strip()[:160])
out2 = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\""
     " | Where-Object { $_.CommandLine -match 'serve-api' }"
     " | ForEach-Object { \"панель: память $([math]::Round($_.WorkingSetSize/1MB)) МБ\" }"],
    capture_output=True, text=True, timeout=60)
print("  %s" % out2.stdout.strip()[:120])
