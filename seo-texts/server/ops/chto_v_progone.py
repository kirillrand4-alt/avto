# -*- coding: utf-8 -*-
"""Что записал журнал по модели: попытки, брак, причины."""
import io
import json
import sys
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
МОДЕЛЬ = sys.argv[1]
N = int(next((a for a in sys.argv[2:] if a.isdigit()), "30"))

строки = []
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                                  # noqa: BLE001
        continue
    if str(z.get("модель") or "") == МОДЕЛЬ:
        строки.append(z)
строки = строки[-N:]
print(f"строк по {МОДЕЛЬ}: {len(строки)}")
эт = Counter(str(z.get("этап") or "—") for z in строки)
print("этапы:", dict(эт))
for z in строки:
    б = z.get("брак")
    т = б if isinstance(б, str) else ("; ".join(map(str, б)) if б else "")
    print(f"  [{z.get('этап') or '—':<13}] ок={z.get('ок')} "
          f"{str(z.get('имя'))[:34]:<34} ${z.get('цена_$')} "
          f"{т[:110]}")
