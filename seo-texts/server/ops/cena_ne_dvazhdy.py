# -*- coding: utf-8 -*-
"""Не считаем ли мы цену партии на каждом письме партии.

17.08 такая ошибка уже была: цену прогона по ИНН приписывали каждой попытке
и получили $86 вместо $62. Прежде чем говорить владельцу сумму, проверяем:
не совпадают ли цена и число вызовов у писем, сделанных одним вызовом.
"""
import io
import json
from collections import Counter, defaultdict

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
группы = defaultdict(list)
строк = 0
сумма = 0.0
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") in ("итог", "отмена_попытки"):
        continue
    строк += 1
    ц = float(z.get("цена_$") or 0)
    сумма += ц
    # признак одной пачки: одинаковые цена+вызовы+секунды
    ключ = (round(ц, 6), int(z.get("вызовов") or 0),
            round(float(z.get("сек") or 0), 1))
    группы[ключ].append(z.get("inn"))

размеры = Counter(len(v) for v in группы.values())
print(f"строк: {строк}, сумма цен: ${сумма:.2f}")
print("сколько строк делят одинаковые (цена, вызовы, секунды):")
for k in sorted(размеры):
    print(f"  по {k} строк: {размеры[k]} групп")
дубли = sum((len(v) - 1) for v in группы.values() if len(v) > 1)
уник = sum(k[0] for k in группы)
print(f"\nстрок-дублей внутри пачек: {дубли}")
print(f"сумма ПО ГРУППАМ (пачка считается один раз): ${уник:.2f}")
