# -*- coding: utf-8 -*-
"""ТОЛЬКО ЧТЕНИЕ: идёт ли заливка, что уже легло. Ничего не снимает."""
import io
import os
import sqlite3
import subprocess
import time

БАЗА = r"C:\sender\enrich.db"
КАТАЛОГ = r"C:\sender\_ops"

проц = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*zalit_kody*' } | "
     "ForEach-Object { \"PID $($_.ProcessId) старт $($_.CreationDate)\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

логи = []
for имя in sorted(os.listdir(КАТАЛОГ)):
    if имя.startswith("zalit_kody_v_requisites-"):
        п = os.path.join(КАТАЛОГ, имя)
        логи.append((os.path.getmtime(п), имя, os.path.getsize(п), п))
логи.sort(reverse=True)

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
наших = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro'").fetchone()[0]
всего = c.execute("SELECT COUNT(*) FROM requisites").fetchone()[0]
c.close()

print("=" * 68)
print("=== СВОДКА: ИДЁТ ЛИ ЗАЛИВКА (только чтение) ===")
print("процесс: %s" % (проц if проц else "НЕ ЗАПУЩЕН"))
print("сейчас:  %s" % time.strftime("%d.%m %H:%M:%S"))
print("")
print("строк с меткой checko-sbor-agro: %d (всего в requisites %d)"
      % (наших, всего))
print("")
print("логи прогонов:")
for мт, имя, рз, п in логи[:3]:
    print("   %-44s %7d Б  %s"
          % (имя, рз, time.strftime("%H:%M:%S", time.localtime(мт))))
if логи and логи[0][2] > 0:
    print("")
    print("=== ХВОСТ СВЕЖЕГО ЛОГА ===")
    for с in io.open(логи[0][3], encoding="utf-8",
                     errors="replace").read().splitlines()[-24:]:
        print("   " + с[:150])
