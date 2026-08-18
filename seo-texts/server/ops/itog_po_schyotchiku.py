# -*- coding: utf-8 -*-
"""Цена письма по счётчику шлюза: от первого калиброванного замера до последнего.

Отдельные замеры по три-пять писем шумят: письмо с двумя кругами починки
стоит втрое дороже соседнего. Берём весь отрезок, где счётчик и число писем
снимались вместе.
"""
import io
import json

Ж = r"C:\sender\_ops\schyotchik-shlyuza.jsonl"
замеры = []
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("писем_в_журнале"):
        замеры.append(z)
if len(замеры) < 2:
    print("калиброванных замеров меньше двух")
    raise SystemExit(0)
a, b = замеры[0], замеры[-1]
d = float(b["total_usage"]) - float(a["total_usage"])
n = int(b["писем_в_журнале"]) - int(a["писем_в_журнале"])
print(f"замеров: {len(замеры)}")
print(f"с {str(a['ts'])[11:19]} по {str(b['ts'])[11:19]}")
print(f"счётчик: {a['total_usage']:.2f} -> {b['total_usage']:.2f} "
      f"(+{d:.2f} единиц)")
print(f"писем в журнале: {a['писем_в_журнале']} -> {b['писем_в_журнале']} "
      f"(+{n})")
# Сколько из этих попыток дали письмо: цена ГОТОВОГО письма это цена попытки,
# делённая на долю удачных.
строки = []
for s2 in io.open(r"C:\sender\_ops\peregeneraciya-braka.jsonl",
                  encoding="utf-8", errors="replace"):
    if s2.strip():
        строки.append(s2)
удачных = 0
for s2 in строки[-n:] if n > 0 else []:
    try:
        удачных += 1 if json.loads(s2).get("ок") else 0
    except Exception:                                            # noqa: BLE001
        pass
if n > 0:
    print(f"\nна попытку: {d/n:.2f} единиц = ${d/n/100:.4f} (если единица цент)")
    print(f"из {n} попыток дали письмо: {удачных}")
    if удачных:
        print(f"на ГОТОВОЕ письмо: ${d/удачных/100:.4f}")
    print("для сравнения по журналу партии (старый конвейер, opus на всём):")
    print("  средняя попытка $0.2048, готовое письмо $0.3188")
