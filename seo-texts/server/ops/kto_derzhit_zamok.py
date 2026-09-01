# -*- coding: utf-8 -*-
"""ТОЛЬКО ЧТЕНИЕ: давно ли чужой оп держит замок и растёт ли WAL."""
import os
import subprocess
import time

БАЗА = r"C:\sender\enrich.db"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


писцы = пш(
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -like '*sverka_prigovorov*' -or "
    "$_.CommandLine -like '*enrich_contacts*' -or "
    "$_.CommandLine -like '*zalit_kody*' } | ForEach-Object { "
    "\"$($_.ProcessId)|$($_.CreationDate)|\" + "
    "$_.CommandLine.Substring(0,[Math]::Min(70,$_.CommandLine.Length)) }")

вал1 = os.path.getsize(БАЗА + "-wal") if os.path.exists(БАЗА + "-wal") else 0
time.sleep(45)
вал2 = os.path.getsize(БАЗА + "-wal") if os.path.exists(БАЗА + "-wal") else 0

# проба записи с терпением в 20 секунд
import sqlite3                                                 # noqa: E402
проба = ""
t0 = time.time()
try:
    w = sqlite3.connect(БАЗА, timeout=20)
    w.execute("PRAGMA busy_timeout = 20000")
    w.execute("CREATE TABLE IF NOT EXISTS _proba_zamka (x INTEGER)")
    w.commit()
    w.execute("DROP TABLE _proba_zamka")
    w.commit()
    w.close()
    проба = "прошла за %.1f с" % (time.time() - t0)
except Exception as ex:                                        # noqa: BLE001
    проба = "НЕ прошла за %.1f с: %s" % (time.time() - t0, str(ex)[:70])

print("=" * 68)
print("=== СВОДКА: КТО ДЕРЖИТ ЗАМОК ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("")
print("процессы, работающие с enrich.db:")
for с in (писцы or "нет").splitlines():
    print("   " + с[:110])
print("")
print("enrich.db-wal: было %d Б, через 45 с стало %d Б (прирост %+d)"
      % (вал1, вал2, вал2 - вал1))
print("проба записи с терпением 20 с: %s" % проба)
