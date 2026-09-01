# -*- coding: utf-8 -*-
"""ТОЛЬКО ЧТЕНИЕ: как идёт ходилка в мобильном режиме."""
import io
import json
import os
import subprocess
import time

КАТАЛОГ = r"C:\sender\_ops"
ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"

проц = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*checko_finansy*' } | "
     "ForEach-Object { $м = [int]((New-TimeSpan -Start $_.CreationDate "
     "-End (Get-Date)).TotalMinutes); \"PID $($_.ProcessId) $м мин\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

логи = []
for имя in sorted(os.listdir(КАТАЛОГ)):
    if имя.startswith("checko_finansy-") and имя.endswith((".log", ".err")):
        п = os.path.join(КАТАЛОГ, имя)
        логи.append((os.path.getmtime(п), имя, os.path.getsize(п), п))
логи.sort(reverse=True)

строк = сбоев = удач = 0
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        строк += 1
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if z.get("сбой"):
            сбоев += 1
        else:
            удач += 1

print("=" * 74)
print("=== СВОДКА: ХОДИЛКА В МОБИЛЬНОМ РЕЖИМЕ ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("процесс: %s" % (проц if проц else "НЕ ЗАПУЩЕН"))
print("")
print("журнал: строк %d (удач %d, сбоев %d)" % (строк, удач, сбоев))
print("")
for мт, имя, рз, п in логи[:3]:
    print("   %-42s %7d Б  %s"
          % (имя, рз, time.strftime("%H:%M:%S", time.localtime(мт))))
for мт, имя, рз, п in логи[:2]:
    if рз > 0 and имя.endswith(".log"):
        print("")
        print("=== %s ===" % имя)
        for с in io.open(п, encoding="utf-8",
                         errors="replace").read().splitlines()[-14:]:
            print("   " + с[:150])
        break
for мт, имя, рз, п in логи[:3]:
    if рз > 0 and имя.endswith(".err"):
        print("")
        print("=== ОШИБКИ %s ===" % имя)
        for с in io.open(п, encoding="utf-8",
                         errors="replace").read().splitlines()[-8:]:
            print("   " + с[:150])
        break
