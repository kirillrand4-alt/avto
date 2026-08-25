# -*- coding: utf-8 -*-
"""Идёт ли прогон 25.08: журнал блоков, хвост лога и счёт написанного."""
import io
import json
import os
import time

КАТАЛОГ = r"C:\sender\_ops"
ОТЧЁТ = os.path.join(КАТАЛОГ, "ochered-25-08.jsonl")
print("=== ЖУРНАЛ БЛОКОВ ===")
if os.path.exists(ОТЧЁТ):
    for с in io.open(ОТЧЁТ, encoding="utf-8").read().splitlines():
        try:
            з = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        когда = time.strftime("%H:%M:%S", time.localtime(з.get("ts", 0)))
        print("   %s %s" % (когда, {к: v for к, v in з.items() if к != "ts"}))
else:
    print("   журнала нет — прогон ещё не начинался")

for имя in sorted(os.listdir(КАТАЛОГ)):
    if not имя.startswith("ochered2508-blok"):
        continue
    п = os.path.join(КАТАЛОГ, имя)
    строки = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    print("\n=== %s (%d строк, обновлён %s) ==="
          % (имя, len(строки),
             time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
    for с in строки[-14:]:
        print("   %s" % с[:150])

# Сколько писем реально написано этим прогоном — по журналу генерации.
ЖУРНАЛ = os.path.join(КАТАЛОГ, "gen-partiya-935.jsonl")
если = os.path.getsize(ЖУРНАЛ) if os.path.exists(ЖУРНАЛ) else 0
print("\nжурнал генерации: %d б, обновлён %s"
      % (если, time.strftime("%H:%M:%S", time.localtime(
          os.path.getmtime(ЖУРНАЛ))) if если else "нет"))
