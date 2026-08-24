# -*- coding: utf-8 -*-
"""Идёт ли прогон тысячи и читается ли кэш у sonnet-конвейера."""
import glob
import io
import json
import os
import subprocess
import time

из = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Select-Object ProcessId,CommandLine | ConvertTo-Csv -NoTypeInformation"],
    capture_output=True, text=True, timeout=120).stdout
живы = [с.strip()[:170] for с in из.splitlines()
        if "tysyacha_sonnet" in с or "partiya_gen" in с]
print("=== ПРОЦЕССЫ ===")
for с in живы:
    print("  " + с)
if not живы:
    print("  прогона НЕТ")

п = r"C:\sender\_ops\tysyacha-sonnet.jsonl"
if os.path.exists(п):
    print("\n=== ОТЧЁТ ДРАЙВЕРА ===")
    for с in io.open(п, encoding="utf-8"):
        if с.strip():
            print("  " + json.dumps(json.loads(с), ensure_ascii=False)[:150])

for л in sorted(glob.glob(r"C:\sender\_ops\tysyacha-blok*.log"),
                key=lambda x: -os.path.getmtime(x))[:1]:
    print("\n=== ХВОСТ %s (%.1f мин назад) ==="
          % (os.path.basename(л), (time.time() - os.path.getmtime(л)) / 60.0))
    for с in io.open(л, encoding="utf-8", errors="replace").readlines()[-10:]:
        print("  " + с.rstrip()[:150])

print("\n=== КЭШ У СВЕЖИХ ПИСЕМ (журнал партии) ===")
ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
записи = []
for с in io.open(ж, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("вход_кэш_запись") is not None and з.get("модель"):
        записи.append(з)
свежие = записи[-40:]
зап = sum(int(з.get("вход_кэш_запись") or 0) for з in свежие)
чт = sum(int(з.get("вход_кэш_чтение") or 0) for з in свежие)
всего = зап + чт
print("  последние %d писем: запись %d, чтение %d → доля чтения %.1f%%"
      % (len(свежие), зап, чт, 100.0 * чт / всего if всего else 0))
for з in свежие[-6:]:
    з_, ч_ = int(з.get("вход_кэш_запись") or 0), int(з.get("вход_кэш_чтение") or 0)
    в = з_ + ч_
    print("    %-34s запись %7d чтение %7d  %4.0f%%  %s"
          % (str(з.get("имя"))[:34], з_, ч_, 100.0 * ч_ / в if в else 0,
             з.get("модель")))
