# -*- coding: utf-8 -*-
"""Жив ли прогон, растёт ли журнал, чем зовётся гейт и сколько max_tokens."""
import io
import json
import os
import re
import subprocess
import sys
import time

КАТАЛОГ = r"C:\sender\_ops"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"

вых = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
     "ForEach-Object { \"$($_.ProcessId) cpu=$($_.UserModeTime/10000000)s\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()
print("=== ПРОЦЕСС ===")
print(вых if вых else "   прогон УМЕР")

for имя in sorted(os.listdir(КАТАЛОГ)):
    if имя.startswith("partiya_gen-0901-052621"):
        п = os.path.join(КАТАЛОГ, имя)
        print("   %-40s %8d Б  изменён %s"
              % (имя, os.path.getsize(п),
                 time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))

# журнал: что дописано после старта прогона
старт = 1788229581  # 05:26:21 по метке файла
свежих, ок, брак = 0, 0, 0
хвост = []
if os.path.exists(ЖУРНАЛ):
    строки = io.open(ЖУРНАЛ, encoding="utf-8", errors="replace").read().splitlines()
    for стр in строки[-400:]:
        try:
            z = json.loads(стр)
        except Exception:  # noqa: BLE001
            continue
        хвост.append(z)
print("")
print("=== ЖУРНАЛ ===")
print("   размер %d Б, изменён %s"
      % (os.path.getsize(ЖУРНАЛ),
         time.strftime("%d.%m %H:%M:%S",
                       time.localtime(os.path.getmtime(ЖУРНАЛ)))))
for z in хвост[-6:]:
    print("   %-16s %-30s ок=%s $%s"
          % (str(z.get("этап"))[:16], str(z.get("имя"))[:30],
             z.get("ок"), z.get("цена_$")))

# чем зовётся гейт
print("")
print("=== ВЫЗОВ ГЕЙТА В partiya_gen ===")
s = io.open(os.path.join(КАТАЛОГ, "partiya_gen.py"),
            encoding="utf-8", errors="replace").read().splitlines()
for i, стр in enumerate(s):
    if "def линза" in стр or "МОДЕЛЬ_ГЕЙТА" in стр or "ПАЧКА" in стр:
        а, б = max(0, i - 4), min(len(s), i + 12)
        for j in range(а, б):
            print("%5d| %s" % (j + 1, s[j][:130]))
        print("   ---")
        if i > 780:
            break

print("")
print("=== max_tokens И ПАЧКА В target_gate ===")
t = io.open(r"C:\sender\sender\target_gate.py",
            encoding="utf-8", errors="replace").read().splitlines()
for i, стр in enumerate(t):
    if re.search(r"max_tokens|_caller\(|пачк|batch|def _ask", стр):
        print("%5d| %s" % (i + 1, стр[:140]))
