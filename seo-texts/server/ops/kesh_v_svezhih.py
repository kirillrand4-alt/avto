# -*- coding: utf-8 -*-
"""Читается ли кэш в САМЫХ СВЕЖИХ письмах: последние N записей журнала."""
import io
import json
import sys
from collections import defaultdict

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
N = int(next((a for a in sys.argv[1:] if a.isdigit()), "40"))
строки = []
for s in io.open(Ж, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "итог":
        строки.append(z)
по = defaultdict(lambda: {"n": 0, "зап": 0, "чт": 0, "цена": 0.0, "ок": 0})
for z in строки[-N:]:
    к = по[str(z.get("модель"))]
    к["n"] += 1
    к["зап"] += int(z.get("вход_кэш_запись") or 0)
    к["чт"] += int(z.get("вход_кэш_чтение") or 0)
    к["цена"] += float(z.get("цена_$") or 0)
    к["ок"] += 1 if z.get("ок") else 0
print(f"последние {N} писем журнала:\n")
print(f"{'модель':<24} {'писем':>6} {'годных':>7} {'зап. в кэш':>11} "
      f"{'прочитано':>10} {'чт/зап':>7} {'$ попытка':>10}")
for м, к in по.items():
    о = к["чт"] / к["зап"] if к["зап"] else 0
    print(f"{м:<24} {к['n']:>6} {к['ок']:>7} {к['зап']:>11} {к['чт']:>10} "
          f"{о:>7.2f} {к['цена'] / к['n']:>10.3f}")
