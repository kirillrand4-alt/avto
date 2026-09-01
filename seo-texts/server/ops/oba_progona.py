# -*- coding: utf-8 -*-
"""ТОЛЬКО ЧТЕНИЕ: идут ли заливка и ходилка, что уже добыто."""
import io
import json
import os
import sqlite3
import subprocess
import time

БАЗА = r"C:\sender\enrich.db"
КАТАЛОГ = r"C:\sender\_ops"
ЖУРНАЛ_ХОД = r"C:\sender\server\checko_finansy.jsonl"

проц = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*zalit_kody*' -or "
     "$_.CommandLine -like '*checko_finansy*' } | ForEach-Object { "
     "  $м = [int]((New-TimeSpan -Start $_.CreationDate -End (Get-Date))"
     ".TotalMinutes); \"PID $($_.ProcessId) $м мин | \" + "
     "$_.CommandLine.Substring(0,[Math]::Min(80,$_.CommandLine.Length)) }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
всего = c.execute("SELECT COUNT(*) FROM requisites").fetchone()[0]
наших = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro'").fetchone()[0]
с_выручкой = c.execute(
    "SELECT COUNT(*) FROM requisites "
    " WHERE COALESCE(revenue_rub,'') NOT IN ('','0')").fetchone()[0]
наших_с_выручкой = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro' "
    "   AND COALESCE(revenue_rub,'') NOT IN ('','0')").fetchone()[0]
от_30 = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro' "
    "   AND CAST(COALESCE(revenue_rub,'0') AS INTEGER) >= 30000000"
).fetchone()[0]
c.close()

ход_строк = 0
if os.path.exists(ЖУРНАЛ_ХОД):
    ход_строк = sum(1 for _ in io.open(ЖУРНАЛ_ХОД, encoding="utf-8",
                                       errors="replace"))

логи = []
for имя in sorted(os.listdir(КАТАЛОГ)):
    if имя.startswith(("zalit_kody_v_requisites-", "checko_finansy-")) \
            and имя.endswith(".log"):
        п = os.path.join(КАТАЛОГ, имя)
        логи.append((os.path.getmtime(п), имя, os.path.getsize(п), п))
логи.sort(reverse=True)

print("=" * 70)
print("=== СВОДКА: ЗАЛИВКА И ХОДИЛКА ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("")
print("процессы:")
for с in (проц or "   НИ ОДНОГО").splitlines():
    print("   " + с[:110])
print("")
print("requisites: всего %d строк, из сбора по Чеко %d" % (всего, наших))
print("   выручка есть у %d строк всего, из них наших %d"
      % (с_выручкой, наших_с_выручкой))
print("   наших с выручкой ОТ 30 МЛН: %d   <- пополнение пула генерации"
      % от_30)
print("")
print("журнал ходилки: %d записей" % ход_строк)
print("")
print("свежие логи:")
for мт, имя, рз, п in логи[:4]:
    print("   %-46s %7d Б  %s"
          % (имя, рз, time.strftime("%H:%M:%S", time.localtime(мт))))
for мт, имя, рз, п in логи[:2]:
    if рз > 0:
        print("")
        print("=== %s ===" % имя)
        for с in io.open(п, encoding="utf-8",
                         errors="replace").read().splitlines()[-8:]:
            print("   " + с[:150])
