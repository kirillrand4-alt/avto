# -*- coding: utf-8 -*-
"""Где сейчас прогон: журнал блоков, шапка и итог каждого лога."""
import io
import json
import os
import time

КАТАЛОГ = r"C:\sender\_ops"
сейчас = time.time()
print("=== ЖУРНАЛ БЛОКОВ ===")
п = os.path.join(КАТАЛОГ, "ochered-25-08.jsonl")
for с in io.open(п, encoding="utf-8").read().splitlines():
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    когда = time.strftime("%H:%M:%S", time.localtime(з.get("ts", 0)))
    print("   %s %s" % (когда, json.dumps(
        {к: v for к, v in з.items() if к != "ts"}, ensure_ascii=False)[:170]))

for имя in sorted(os.listdir(КАТАЛОГ)):
    if not имя.startswith("ochered2508-blok"):
        continue
    п = os.path.join(КАТАЛОГ, имя)
    ст = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    print("\n=== %s: %d строк, обновлён %.1f мин назад ==="
          % (имя, len(ст), (сейчас - os.path.getmtime(п)) / 60.0))
    for с in ст[:12]:
        print("   %s" % с[:140])
    if len(ст) > 14:
        print("   ...")
        for с in ст[-3:]:
            print("   %s" % с[:140])
