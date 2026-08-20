# -*- coding: utf-8 -*-
"""Итог по модели прямо из журнала: годных, потрачено, цена за годное.

Нужен, когда раннер потерял вывод по таймауту, а письма в журнале есть.
"""
import io
import json
import sys
from collections import defaultdict

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "10"))
МОДЕЛИ = [a for a in sys.argv[1:] if not a.isdigit()]

по = defaultdict(list)
for s in io.open(Ж, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "итог":
        по[str(z.get("модель"))].append(z)

print(f"{'модель':<26} {'годных':>7} {'из':>4} {'$ всего':>9} "
      f"{'$ за годное':>12} {'$ попытка':>10} {'сек':>5}")
for м in (МОДЕЛИ or sorted(по)):
    кусок = по.get(м, [])[-СКОЛЬКО:]
    if not кусок:
        print(f"{м:<26} — писем нет")
        continue
    г = sum(1 for x in кусок if x.get("ок"))
    п = sum(float(x.get("цена_$") or 0) for x in кусок)
    сек = sum(int(x.get("сек") or 0) for x in кусок) / len(кусок)
    за = f"${п / г:.2f}" if г else "—"
    print(f"{м:<26} {г:>7} {len(кусок):>4} {п:>9.2f} {за:>12} "
          f"{п / len(кусок):>10.3f} {сек:>5.0f}")
