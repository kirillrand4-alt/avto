# -*- coding: utf-8 -*-
"""Пошёл ли перезапущенный блок КЦ без предклассификатора."""
import io
import json
import os
import subprocess
import time

КАТАЛОГ = r"C:\sender\_ops"
сейчас = time.time()
в = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*'} | "
     "Select-Object ProcessId,@{n='cmd';e={$_.CommandLine}} | ConvertTo-Json -Compress"],
    capture_output=True, timeout=60)
т = (в.stdout or b"").decode("utf-8", "replace").strip()
print("=== ПРОЦЕССЫ ГЕНЕРАЦИИ ===")
if т:
    д = json.loads(т)
    for п in (д if isinstance(д, list) else [д]):
        print("   pid %-7s %s" % (п["ProcessId"], str(п["cmd"])[:120]))
else:
    print("   нет процессов partiya_gen")

for имя in ("ochered2508-blok2b-kc.log", "ochered2508-blok2b-kc.log.err"):
    п = os.path.join(КАТАЛОГ, имя)
    if not os.path.exists(п):
        print("\n%s — файла нет" % имя)
        continue
    ст = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    print("\n=== %s: %d строк, обновлён %.1f мин назад ==="
          % (имя, len(ст), (сейчас - os.path.getmtime(п)) / 60.0))
    for с in ст[-14:]:
        print("   %s" % с[:150])
