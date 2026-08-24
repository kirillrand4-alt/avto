# -*- coding: utf-8 -*-
"""Во что обходится письмо прямо сейчас, на идущем прогоне."""
import glob
import io
import json
import os
import re
import time

print("=== ИДУЩИЙ БЛОК ===")
for л in sorted(glob.glob(r"C:\sender\_ops\tysyacha-blok*.log"),
                key=lambda x: -os.path.getmtime(x))[:1]:
    строки = io.open(л, encoding="utf-8", errors="replace").readlines()
    письма = [с for с in строки if re.search(r"\[\d+/\d+\]", с)]
    ок = [с for с in письма if "] ОК " in с]
    цены = [float(m.group(1)) for с in письма
            for m in [re.search(r"\$([\d.]+)", с)] if m]
    print("  %s, обновлён %.1f мин назад"
          % (os.path.basename(л), (time.time() - os.path.getmtime(л)) / 60.0))
    print("  попыток %d, годных %d (%.0f%%)"
          % (len(письма), len(ок), 100.0 * len(ок) / len(письма) if письма else 0))
    if цены:
        потрачено = sum(цены)
        print("  потрачено $%.2f | за попытку $%.4f | ЗА ГОДНОЕ ПИСЬМО $%.4f"
              % (потрачено, потрачено / len(цены),
                 потрачено / len(ок) if ок else 0))
    for с in письма[-5:]:
        print("    " + с.rstrip()[:130])

print("\n=== СЕГОДНЯ ПО ЖУРНАЛУ, ПО МОДЕЛЯМ ===")
ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
по_модели = {}
for с in io.open(ж, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("этап") != "итог" or з.get("цена_$") is None:
        continue
    м = str(з.get("модель") or "?")
    д = по_модели.setdefault(м, {"попыток": 0, "годных": 0, "цена": 0.0})
    д["попыток"] += 1
    д["цена"] += float(з.get("цена_$") or 0)
    if з.get("ок"):
        д["годных"] += 1
for м, д in sorted(по_модели.items(), key=lambda x: -x[1]["попыток"]):
    if д["попыток"] < 5:
        continue
    print("  %-22s попыток %5d, годных %5d (%3.0f%%), $%.4f за годное"
          % (м, д["попыток"], д["годных"],
             100.0 * д["годных"] / д["попыток"],
             д["цена"] / д["годных"] if д["годных"] else 0))
