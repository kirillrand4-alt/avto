# -*- coding: utf-8 -*-
"""Каким прогоном и на какой модели делали письма в последний раз."""
import io
import json
import os
import time
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
строки = []
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f:
        try:
            строки.append(json.loads(с))
        except Exception:                                     # noqa: BLE001
            pass
print("строк в журнале: %d" % len(строки))
print("ключи последней строки: %s" % sorted(строки[-1].keys())[:20])

последние = строки[-1500:]
модели = Counter(str(z.get("модель") or z.get("model") or "") for z in последние)
print("\nмодели в последних 1500 строках:")
for м, n in модели.most_common(6):
    print("   %-26s %5d" % (м or "(не записана)", n))

цены = [z.get("цена") or z.get("$") or z.get("cena") for z in последние]
цены = [float(c) for c in цены if isinstance(c, (int, float))]
if цены:
    цены.sort()
    print("\nцена письма в последних строках: медиана $%.3f, среднее $%.3f, "
          "максимум $%.3f (n=%d)"
          % (цены[len(цены) // 2], sum(цены) / len(цены), цены[-1], len(цены)))

этапы = Counter(str(z.get("этап") or "") for z in последние)
print("\nэтапы: %s" % dict(этапы))

# когда последние записи
for z in строки[-3:]:
    т = z.get("ts") or z.get("время")
    когда = ""
    if isinstance(т, (int, float)):
        когда = time.strftime("%d.%m %H:%M", time.localtime(т))
    print("   %-14s inn=%-13s этап=%-14s %s"
          % (когда, z.get("inn"), z.get("этап"), str(z.get("модель") or "")[:24]))

print("\n=== ХВОСТЫ ЛОГОВ ПРОГОНОВ ===")
import glob
for п in sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
                key=os.path.getmtime, reverse=True)[:3]:
    print("\n-- %s (%.1f ч назад)"
          % (os.path.basename(п), (time.time() - os.path.getmtime(п)) / 3600))
    с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for x in с[:4]:
        print("   %s" % x[:140])
    print("   …")
    for x in с[-6:]:
        print("   %s" % x[:140])
