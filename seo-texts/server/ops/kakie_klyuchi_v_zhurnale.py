# -*- coding: utf-8 -*-
"""Какие ключи реально пишет журнал генерации — чтобы считать по фактам."""
import io
import json
import os
import sys
from collections import Counter

путь = sys.argv[1] if len(sys.argv) > 1 else r"C:\sender\_ops\gen-partiya-935.jsonl"
if not os.path.exists(путь):
    print("нет файла:", путь); raise SystemExit(1)
ключи = Counter()
этапы = Counter()
примеры = {}
n = 0
for s in io.open(путь, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                                  # noqa: BLE001
        continue
    n += 1
    этапы[str(z.get("этап") or "—")] += 1
    for k, v in z.items():
        ключи[k] += 1
        if k not in примеры and not isinstance(v, (dict, list)):
            примеры[k] = str(v)[:60]
        elif k not in примеры:
            примеры[k] = json.dumps(v, ensure_ascii=False)[:120]
print(f"строк: {n}")
print("\nэтапы:", dict(этапы))
print("\nключи:")
for k, v in ключи.most_common():
    print(f"  {v:>7}  {k:<20} пример: {примеры.get(k, '')}")
