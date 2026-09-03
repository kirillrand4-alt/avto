# -*- coding: utf-8 -*-
"""ТОЛЬКО ЧТЕНИЕ: как идёт поиск сайтов, доля подтверждённых, баланс."""
import io
import json
import os
import subprocess
import time
import urllib.request
from collections import Counter

ЖУРНАЛ = r"C:\sender\server\sayty_dlya_celey.jsonl"
КАТАЛОГ = r"C:\sender\_ops"

проц = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
     "'*sayty_dlya_celey*' } | ForEach-Object { $м = [int]((New-TimeSpan "
     "-Start $_.CreationDate -End (Get-Date)).TotalMinutes); "
     "\"PID $($_.ProcessId) $м мин\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

бал = "?"
try:
    о = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    з = urllib.request.Request(
        "http://xmlriver.com/api/get_balance/?user=%s&key=%s"
        % (os.environ.get("XMLRIVER_USER", ""),
           os.environ.get("XMLRIVER_KEY", "")))
    бал = о.open(з, timeout=25).read().decode().strip()
except Exception as ex:                                        # noqa: BLE001
    бал = "не спросился: %s" % str(ex)[:60]

# журнал: считаем ВЕСЬ и сегодняшний хвост
всего = Counter()
хвост = []
if os.path.exists(ЖУРНАЛ):
    стр = io.open(ЖУРНАЛ, encoding="utf-8", errors="replace").read().splitlines()
    for с in стр:
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        сайт = str(z.get("сайт") or "")
        совпал = str(z.get("инн_на_странице") or "")
        if not сайт:
            всего["сайт не найден"] += 1
        elif совпал in ("True", "true", "1"):
            всего["ПОДТВЕРЖДЁН (ИНН на странице)"] += 1
        else:
            всего["кандидат (ИНН не подтвердился)"] += 1
    хвост = стр[-6:]

логи = sorted((os.path.getmtime(os.path.join(КАТАЛОГ, и)), и)
              for и in os.listdir(КАТАЛОГ) if и.startswith("poisk_saytov-"))

print("=" * 76)
print("=== СВОДКА: ПОИСК САЙТОВ ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("процесс: %s" % (проц if проц else "НЕ ЗАПУЩЕН"))
print("баланс XMLRiver: %s" % бал)
print("")
итог = sum(всего.values())
print("записей в журнале всего: %d" % итог)
for к, в in всего.most_common():
    print("   %-34s %6d  (%4.1f%%)" % (к, в, 100.0 * в / итог if итог else 0))
print("")
for мт, и in логи[-2:]:
    п = os.path.join(КАТАЛОГ, и)
    print("   %-40s %7d Б  %s" % (и, os.path.getsize(п),
                                  time.strftime("%H:%M:%S",
                                                time.localtime(мт))))
    if os.path.getsize(п) > 0 and и.endswith(".log"):
        for с in io.open(п, encoding="utf-8",
                         errors="replace").read().splitlines()[-8:]:
            print("      " + с[:140])
