# -*- coding: utf-8 -*-
"""Что сказал шлюз, сколько писем успели и во что обошлись."""
import glob
import io
import json
import os
import re
import time

print("=== ОТЧЁТ ДРАЙВЕРА ===")
п = r"C:\sender\_ops\tysyacha-sonnet.jsonl"
if os.path.exists(п):
    for с in io.open(п, encoding="utf-8"):
        if с.strip():
            print("  " + json.dumps(json.loads(с), ensure_ascii=False)[:170])

print("\n=== ЧТО ИМЕННО ОТВЕТИЛ ШЛЮЗ ===")
показано = 0
for л in sorted(glob.glob(r"C:\sender\_ops\tysyacha-blok*.log"),
                key=lambda x: -os.path.getmtime(x)):
    for с in io.open(л, encoding="utf-8", errors="replace"):
        if "403" in с and показано < 3:
            показано += 1
            print("  " + с.strip()[:300])
    if показано:
        break

print("\n=== ИТОГИ БЛОКОВ ===")
for л in sorted(glob.glob(r"C:\sender\_ops\tysyacha-blok*.log")):
    строки = io.open(л, encoding="utf-8", errors="replace").readlines()
    письма = [с for с in строки if re.search(r"\[\d+/\d+\]", с)]
    ок = [с for с in письма if "] ОК " in с]
    п403 = [с for с in письма if "403" in с]
    итог = next((с.strip() for с in reversed(строки) if с.startswith("итог:")), "")
    цены = [float(m.group(1)) for с in письма
            for m in [re.search(r"\$([\d.]+)", с)] if m]
    print("  %s: попыток %d, годных %d, упало по 403: %d, потрачено $%.2f"
          % (os.path.basename(л), len(письма), len(ок), len(п403), sum(цены)))
    if итог:
        print("     %s" % итог[:120])
    print("     обновлён %.1f мин назад"
          % ((time.time() - os.path.getmtime(л)) / 60.0))

print("\n=== ЖИВ ЛИ ПРОГОН ===")
import subprocess
из = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Select-Object ProcessId,CommandLine | ConvertTo-Csv -NoTypeInformation"],
    capture_output=True, text=True, timeout=120).stdout
живы = [с.strip()[:150] for с in из.splitlines()
        if "tysyacha_sonnet" in с or "partiya_gen" in с]
for с in живы:
    print("  " + с)
if not живы:
    print("  процессов нет")
