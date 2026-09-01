# -*- coding: utf-8 -*-
"""Глушится ли рассуждение в _raw_stream и жив ли прогон. Сводка — В КОНЦЕ."""
import io
import json
import os
import subprocess
import time

s = io.open(r"C:\sender\gen_provider.py", encoding="utf-8",
            errors="replace").read()
i = s.find("def _raw_stream")
j = s.find("\ndef ", i + 10)
кусок = s[i:j if j > 0 else i + 6000]
print("=== _raw_stream (%d знаков) ===" % len(кусок))
print(кусок[:5200])

print("")
print("=== ЧТО В НЁМ ПРО thinking/effort ===")
for n, стр in enumerate(кусок.splitlines(), 1):
    if any(k in стр for k in ("thinking", "effort", "reasoning", "budget")):
        print("%4d| %s" % (n, стр[:150]))

# --- СВОДКА В КОНЦЕ ------------------------------------------------------
проц = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
     "ForEach-Object { \"PID $($_.ProcessId)  процессорного времени "
     "$([int]($_.UserModeTime/10000000))с\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

КАТАЛОГ = r"C:\sender\_ops"
файлы = []
for имя in sorted(os.listdir(КАТАЛОГ)):
    if имя.startswith("partiya_gen-0901-052621"):
        п = os.path.join(КАТАЛОГ, имя)
        файлы.append((имя, os.path.getsize(п), os.path.getmtime(п)))

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
стрк = io.open(ЖУРНАЛ, encoding="utf-8", errors="replace").read().splitlines()
хвост = []
for стр in стрк[-30:]:
    try:
        хвост.append(json.loads(стр))
    except Exception:  # noqa: BLE001
        pass

print("")
print("=" * 62)
print("=== СВОДКА ===")
print("процесс: %s" % (проц if проц else "ПРОГОН УМЕР"))
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
for имя, рз, мт in файлы:
    print("   %-40s %8d Б  изменён %s"
          % (имя, рз, time.strftime("%H:%M:%S", time.localtime(мт))))
print("журнал: %d строк, изменён %s"
      % (len(стрк), time.strftime("%d.%m %H:%M:%S",
                                  time.localtime(os.path.getmtime(ЖУРНАЛ)))))
print("последние записи журнала:")
for z in хвост[-5:]:
    print("   %-16s %-28s ок=%s $%s"
          % (str(z.get("этап"))[:16], str(z.get("имя"))[:28],
             z.get("ок"), z.get("цена_$")))
