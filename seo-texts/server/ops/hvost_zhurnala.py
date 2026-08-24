# -*- coding: utf-8 -*-
"""Последние строки журнала генерации и логи ДВУХ САМЫХ СВЕЖИХ прогонов.

Владелец 24.08: две карточки в очереди за сегодня — это его ручные копии,
а не выработка прогонов. Значит журнал вырос на что-то другое, и надо
увидеть строки целиком, а не счётчик.
"""
import glob
import io
import json
import os
import time

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
строки = io.open(Ж, encoding="utf-8", errors="replace").read().splitlines()
print("строк в журнале: %d, изменён %d с назад"
      % (len(строки), int(time.time() - os.path.getmtime(Ж))))
print("\n=== ПОСЛЕДНИЕ 8 СТРОК ===")
for с in строки[-8:]:
    try:
        з = json.loads(с)
    except Exception:                                          # noqa: BLE001
        print("  (не json):", с[:220])
        continue
    сжато = {}
    for k, v in з.items():
        if k in ("тело", "body", "письмо"):
            сжато[k] = "<%d знаков>" % len(str(v))
        elif isinstance(v, (int, float, bool)) or v is None:
            сжато[k] = v
        else:
            сжато[k] = str(v)[:70]
    print("  " + json.dumps(сжато, ensure_ascii=False)[:600])

print("\n=== ЛОГИ ДВУХ САМЫХ СВЕЖИХ ПРОГОНОВ ===")
логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-0824-*.log"),
              key=os.path.getmtime)[-2:]
for п in логи:
    т = io.open(п, encoding="utf-8", errors="replace").read()
    print("\n-- %s | %d знаков | изменён %d с назад"
          % (os.path.basename(п), len(т), int(time.time() - os.path.getmtime(п))))
    print(т[-1800:])
