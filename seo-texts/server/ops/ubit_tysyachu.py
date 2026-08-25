# -*- coding: utf-8 -*-
"""Снять драйвер тысячи и его текущий блок.

Порядок важен: сперва драйвер, иначе он увидит смерть блока как обычное
завершение и запустит следующий.
"""
import io
import json
import os
import subprocess

вывод = subprocess.run(
    ["wmic", "process", "where", "name='python.exe'", "get",
     "ProcessId,CommandLine", "/format:list"],
    capture_output=True, text=True, timeout=60).stdout
пары, ком = [], ""
for с in вывод.splitlines():
    с = с.strip()
    if с.startswith("CommandLine="):
        ком = с
    elif с.startswith("ProcessId=") and с.split("=", 1)[1].strip():
        пары.append((с.split("=", 1)[1].strip(), ком))

for метка in ("tysyacha_sonnet.py", "partiya_gen.py"):
    цели = [п for п, к in пары if метка in к]
    if not цели:
        print("%s: процессов нет" % метка)
        continue
    for пид in цели:
        r = subprocess.run(["taskkill", "/PID", пид, "/F"],
                           capture_output=True, text=True, timeout=60)
        print("%s pid=%s -> %s" % (метка, пид,
                                   (r.stdout or r.stderr).strip()[:90]))

п = r"C:\sender\_ops\tysyacha-sonnet.jsonl"
if os.path.exists(п):
    print("\n=== ЧТО УСПЕЛ ДРАЙВЕР ===")
    for с in io.open(п, encoding="utf-8"):
        с = с.strip()
        if с:
            з = json.loads(с)
            if з.get("ts", 0) > 1787620000:      # только этот, второй запуск
                print("  " + json.dumps(з, ensure_ascii=False)[:170])

import glob
import re
import time
print("\n=== ТЕКУЩИЙ БЛОК ===")
for л in sorted(glob.glob(r"C:\sender\_ops\tysyacha-blok*.log"),
                key=lambda x: -os.path.getmtime(x))[:1]:
    строки = io.open(л, encoding="utf-8", errors="replace").readlines()
    письма = [с for с in строки if re.search(r"\[\d+/\d+\]", с)]
    ок = [с for с in письма if "] ОК " in с]
    цены = [float(m.group(1)) for с in письма
            for m in [re.search(r"\$([\d.]+)", с)] if m]
    print("  %s (обновлён %.1f мин назад)"
          % (os.path.basename(л), (time.time() - os.path.getmtime(л)) / 60.0))
    print("  попыток %d, годных %d, потрачено $%.2f"
          % (len(письма), len(ок), sum(цены)))
    for с in письма[-4:]:
        print("    " + с.rstrip()[:130])
