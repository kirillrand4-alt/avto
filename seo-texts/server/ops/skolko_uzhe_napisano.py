# -*- coding: utf-8 -*-
"""Сколько писем каждая модель успела написать — живой счётчик по журналу."""
import io
import json
import os
import time
from collections import Counter

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
счёт = Counter()
годных = Counter()
цена = Counter()
for s in io.open(Ж, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") != "итог":
        continue
    м = str(z.get("модель"))
    счёт[м] += 1
    годных[м] += 1 if z.get("ок") else 0
    цена[м] += float(z.get("цена_$") or 0)
st = os.stat(Ж)
print(f"журнал изменён {int(time.time() - st.st_mtime)} с назад\n")
for м, n in счёт.most_common():
    print(f"  {м:<26} всего {n:>5} | годных {годных[м]:>4} | "
          f"${цена[м]:>8.2f}")
