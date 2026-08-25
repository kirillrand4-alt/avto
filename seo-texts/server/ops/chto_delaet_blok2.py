# -*- coding: utf-8 -*-
"""Что успел блок 2 с момента старта: строки журнала после 14:34."""
import io
import json
import os
import time
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
СТАРТ = 1787657659.0     # 14:34:19 по машине, старт блока 2
сейчас = time.time()
print("журнал обновлён %.1f мин назад, размер %d б"
      % ((сейчас - os.path.getmtime(ЖУРНАЛ)) / 60.0, os.path.getsize(ЖУРНАЛ)))

# Читаем хвост: строки блока 2 идут последними.
with io.open(ЖУРНАЛ, "rb") as ф:
    ф.seek(max(0, os.path.getsize(ЖУРНАЛ) - 400000))
    хвост = ф.read().decode("utf-8", "replace").splitlines()[1:]

этапы = Counter()
последние = []
for с in хвост:
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    этапы[str(з.get("этап") or ("ок" if з.get("ок") else "?"))] += 1
    последние.append(з)
print("\nэтапы в хвосте журнала:")
for к, н in этапы.most_common(8):
    print("   %-30s %5d" % (к, н))
print("\nпоследние 6 записей:")
for з in последние[-6:]:
    print("   %s" % json.dumps(
        {к: v for к, v in з.items()
         if к in ("этап", "inn", "имя", "направление", "почему", "модель")},
        ensure_ascii=False)[:150])

лог = r"C:\sender\_ops\ochered2508-blok2-kc.log"
ст = io.open(лог, encoding="utf-8", errors="replace").read().splitlines()
print("\nлог блока 2: %d строк, обновлён %.1f мин назад"
      % (len(ст), (сейчас - os.path.getmtime(лог)) / 60.0))
for с in ст[-6:]:
    print("   %s" % с[:150])
