# -*- coding: utf-8 -*-
"""Почему провайдер перестал молотить: последние строки журнала и процессы."""
import io
import json
import os
import subprocess
import time
from collections import Counter

КАТАЛОГ = r"C:\sender\_ops"
ЖУРНАЛ = os.path.join(КАТАЛОГ, "gen-partiya-935.jsonl")
сейчас = time.time()

print("=== ПРОЦЕССЫ ПРОГОНА ===")
в = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*' -or "
     "$_.CommandLine -like '*ochered_25_08*'} | "
     "Select-Object ProcessId,WorkingSetSize,UserModeTime,"
     "@{n='cmd';e={$_.CommandLine.Substring(0,[Math]::Min(90,$_.CommandLine.Length))}} "
     "| Format-List"], capture_output=True, timeout=60)
т = (в.stdout or b"").decode("cp866", "replace")
print("\n".join("   " + с.strip() for с in т.splitlines() if с.strip()) or "   НЕТ ПРОЦЕССОВ")

print("\n=== ХВОСТ ЖУРНАЛА ГЕНЕРАЦИИ ===")
строки = []
with io.open(ЖУРНАЛ, "rb") as ф:
    ф.seek(max(0, os.path.getsize(ЖУРНАЛ) - 200000))
    строки = ф.read().decode("utf-8", "replace").splitlines()[1:]
print("   всего строк в хвосте: %d, файл обновлён %.1f мин назад"
      % (len(строки), (сейчас - os.path.getmtime(ЖУРНАЛ)) / 60.0))
этапы = Counter()
последние = []
for с in строки:
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    этапы[str(з.get("этап") or ("ок" if з.get("ок") else "?"))] += 1
    последние.append(з)
for к, н in этапы.most_common(10):
    print("   %-32s %5d" % (к, н))
print("\n   последние 8 записей:")
for з in последние[-8:]:
    крат = {к: v for к, v in з.items()
            if к in ("этап", "inn", "имя", "модель", "ок", "почему", "сек",
                     "цена_$", "ошибка", "направление")}
    print("      %s" % json.dumps(крат, ensure_ascii=False)[:150])

print("\n=== ЛОГ БЛОКА ===")
лог = os.path.join(КАТАЛОГ, "ochered2508-blok1-meyer.log")
if os.path.exists(лог):
    ст = io.open(лог, encoding="utf-8", errors="replace").read().splitlines()
    print("   строк %d, обновлён %.1f мин назад"
          % (len(ст), (сейчас - os.path.getmtime(лог)) / 60.0))
    for с in ст[-12:]:
        print("      %s" % с[:150])

сч = os.path.join(КАТАЛОГ, "schyotchik-shlyuza.jsonl")
if os.path.exists(сч):
    print("\n=== СЧЁТЧИК ШЛЮЗА (последние) ===")
    for с in io.open(сч, encoding="utf-8", errors="replace").read().splitlines()[-4:]:
        print("   %s" % с[:170])
