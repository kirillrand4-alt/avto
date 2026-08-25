# -*- coding: utf-8 -*-
"""Доехал ли флаг --bez-predklassa до перезапущенного процесса.

В прошлой проверке командная строка обрезалась ровно на месте флага, а
разница принципиальная: с предклассом на запасной модели блок снова начнёт
выбрасывать своих. Смотрим строку целиком и свежие строки журнала.
"""
import io
import json
import os
import subprocess
import time

в = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*'} | "
     "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
    capture_output=True, timeout=60)
т = (в.stdout or b"").decode("utf-8", "replace").strip()
print("=== КОМАНДНАЯ СТРОКА ЦЕЛИКОМ ===")
if т:
    д = json.loads(т)
    for п in (д if isinstance(д, list) else [д]):
        стр = str(п["CommandLine"])
        print("   pid %s" % п["ProcessId"])
        print("   %s" % стр)
        print("   флаг --bez-predklassa: %s"
              % ("ЕСТЬ" if "bez-predklassa" in стр else "НЕТ"))
else:
    print("   процессов нет")

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
порог = time.time() - 900          # последние 15 минут
with io.open(ЖУРНАЛ, "rb") as ф:
    ф.seek(max(0, os.path.getsize(ЖУРНАЛ) - 400000))
    хвост = ф.read().decode("utf-8", "replace").splitlines()[1:]
свежие = []
for с in хвост:
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if float(з.get("ts") or 0) >= порог:
        свежие.append(з)
from collections import Counter
print("\n=== ЗАПИСИ ЖУРНАЛА ЗА ПОСЛЕДНИЕ 15 МИНУТ: %d ===" % len(свежие))
for к, н in Counter(str(з.get("этап") or "?") for з in свежие).most_common(6):
    print("   %-28s %5d" % (к, н))
for з in свежие[-5:]:
    print("   %s" % json.dumps({к: v for к, v in з.items() if к != "ts"},
                               ensure_ascii=False)[:130])
