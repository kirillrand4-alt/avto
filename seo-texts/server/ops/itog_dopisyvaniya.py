# -*- coding: utf-8 -*-
"""Что дало дописывание зачинов: сколько спасено, как их судил рецензент.

Решающая проверка: спасённое письмо должно быть НЕ ХУЖЕ обычного. Если
рецензент бракует переписанные зачины чаще, дешевизна ничего не стоит.
"""
import io
import json
from collections import Counter

СВОЙ = r"C:\sender\_ops\dopisannye-zachiny.jsonl"
РЕЦ = r"C:\sender\_ops\rezenzii-pisem.jsonl"

верд = {}
for s in io.open(РЕЦ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass

итог = Counter()
вердикты = Counter()
примеры = []
for s in io.open(СВОЙ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    rid = z.get("review_id")
    if z.get("гейт"):
        итог["гейт снова забраковал"] += 1
        continue
    if not rid:
        итог["в очередь не попало"] += 1
        continue
    итог["в очереди"] += 1
    в = верд.get(int(rid)) or "ещё не рецензировано"
    вердикты[в] += 1
    if в == "годно" and len(примеры) < 2:
        примеры.append((rid, z.get("имя"), z.get("тема"), z.get("тело")))

print("дописывание зачинов:")
for k, n in итог.most_common():
    print(f"  {n:>4}  {k}")
print("\nвердикт рецензента у дописанных:")
реш = 0
for k, n in вердикты.most_common():
    print(f"  {n:>4}  {k}")
    if k in ("годно", "не годно"):
        реш += n
г = вердикты.get("годно", 0)
if реш:
    print(f"\nдоля годных среди решённых: {100.0 * г / реш:.0f}% "
          f"({г} из {реш})")
for rid, имя, тема, тело in примеры:
    print("\n" + "=" * 68)
    print(f"#{rid}  {имя}\nТЕМА: {тема}\n\n{тело}")
