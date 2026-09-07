# -*- coding: utf-8 -*-
"""Идёт ли заливка агро и что в её логе."""
import io
import os
import subprocess
import time

КАТАЛОГ = r"C:\sender\_ops"
проц = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
     "'*zalit_agro*' } | ForEach-Object { $м = [int]((New-TimeSpan -Start "
     "$_.CreationDate -End (Get-Date)).TotalMinutes); "
     "\"PID $($_.ProcessId) $м мин\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

логи = []
for имя in sorted(os.listdir(КАТАЛОГ)):
    if имя.startswith("zalit_agro_v_bazu-"):
        п = os.path.join(КАТАЛОГ, имя)
        логи.append((os.path.getmtime(п), имя, os.path.getsize(п), п))
логи.sort(reverse=True)

print("=" * 74)
print("=== СВОДКА: ЗАЛИВКА АГРО ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("процесс: %s" % (проц if проц else "НЕ ЗАПУЩЕН"))
print("")
for мт, имя, рз, п in логи[:4]:
    print("   %-44s %8d Б  %s"
          % (имя, рз, time.strftime("%H:%M:%S", time.localtime(мт))))
for мт, имя, рз, п in логи[:2]:
    if рз > 0:
        print("")
        print("=== %s ===" % имя)
        стр = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
        for с in стр[:12]:
            print("   " + с[:150])
        if len(стр) > 24:
            print("   ...")
        for с in стр[-14:]:
            print("   " + с[:150])
