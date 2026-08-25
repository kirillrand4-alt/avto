# -*- coding: utf-8 -*-
"""Остановить блок КЦ немедленно и показать, что он успел потратить.

В .err-логе подряд «пустой/обрезанный ответ: stop_reason=end_turn
content=['text']» — модель отвечает прозой вместо JSON, вызов считается
сбоем, идёт ретрай, и каждый заход стоит денег без письма на выходе.
"""
import io
import json
import os
import subprocess
import sys
import time

КАТАЛОГ = r"C:\sender\_ops"
ДЕЛАТЬ = "primenit" in sys.argv[1:]

в = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*' -or "
     "$_.CommandLine -like '*ochered_25_08*'} | "
     "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
    capture_output=True, timeout=60)
т = (в.stdout or b"").decode("utf-8", "replace").strip()
процессы = []
if т:
    д = json.loads(т)
    процессы = д if isinstance(д, list) else [д]
for п in процессы:
    print("   pid %-7s %s" % (п["ProcessId"], str(п["CommandLine"])[:120]))

if ДЕЛАТЬ:
    for п in процессы:
        subprocess.run(["taskkill", "/PID", str(п["ProcessId"]), "/F"],
                       capture_output=True, timeout=30)
        print("ОСТАНОВЛЕН pid %s" % п["ProcessId"])
    time.sleep(2)

# Что успел: главный лог блока и деньги по журналу.
лог = os.path.join(КАТАЛОГ, "ochered2508-blok2b-kc.log")
ст = io.open(лог, encoding="utf-8", errors="replace").read().splitlines()
print("\n=== ГЛАВНЫЙ ЛОГ БЛОКА (%d строк) ===" % len(ст))
for с in ст[-16:]:
    print("   %s" % с[:150])

ошибки = os.path.join(КАТАЛОГ, "ochered2508-blok2b-kc.log.err")
э = io.open(ошибки, encoding="utf-8", errors="replace").read().splitlines()
print("\nстрок в .err: %d" % len(э))

ЖУРНАЛ = os.path.join(КАТАЛОГ, "gen-partiya-935.jsonl")
порог = time.time() - 3600
with io.open(ЖУРНАЛ, "rb") as ф:
    ф.seek(max(0, os.path.getsize(ЖУРНАЛ) - 600000))
    хвост = ф.read().decode("utf-8", "replace").splitlines()[1:]
цена = 0.0
записей = 0
from collections import Counter
этапы = Counter()
for с in хвост:
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if float(з.get("ts") or 0) < порог:
        continue
    записей += 1
    этапы[str(з.get("этап") or ("ок" if з.get("ок") else "?"))] += 1
    цена += float(з.get("цена_$") or 0)
print("\n=== ЖУРНАЛ ЗА ЧАС: %d записей, $%.2f ===" % (записей, цена))
for к, н in этапы.most_common(8):
    print("   %-28s %5d" % (к, н))
