# -*- coding: utf-8 -*-
"""Снять ходилку и посчитать, что она успела и что потеряла."""
import io
import json
import os
import subprocess
import time
from collections import Counter

ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


пиды = пш("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
          "-like '*checko_finansy*' } | ForEach-Object { $_.ProcessId }").split()
for п in пиды:
    if п.isdigit():
        пш("Stop-Process -Id %s -Force" % п)
time.sleep(3)

всего, удач, сбоев, с_выручкой = 0, 0, 0, 0
инны_удач, инны_сбоев = set(), set()
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    всего += 1
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    и = "".join(c for c in str(z.get("inn") or "") if c.isdigit())
    if z.get("сбой"):
        сбоев += 1
        инны_сбоев.add(и)
    else:
        удач += 1
        инны_удач.add(и)
        if str(z.get("revenue_rub") or "") not in ("", "0"):
            с_выручкой += 1

print("=" * 70)
print("=== СВОДКА: ХОДИЛКА ОСТАНОВЛЕНА ===")
print("снято процессов: %s" % (", ".join(пиды) if пиды else "не было"))
print("")
print("журнал: строк %d" % всего)
print("   удачных записей:      %6d (компаний %d)" % (удач, len(инны_удач)))
print("   с выручкой:           %6d" % с_выручкой)
print("   сбоев «не достучались»:%6d (компаний %d)"
      % (сбоев, len(инны_сбоев)))
print("   из них НЕ добыты вовсе: %5d" % len(инны_сбоев - инны_удач))
