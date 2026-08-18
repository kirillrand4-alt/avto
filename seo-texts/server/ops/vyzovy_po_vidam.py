# -*- coding: utf-8 -*-
"""Разбивка вызовов модели по видам — что резать дальше."""
import io
import json
from collections import Counter

Ж = r"C:\sender\_ops\peregeneraciya-braka.jsonl"
виды = Counter()
писем = 0
всего = 0
исходы = Counter()
для_ок = Counter()
ок_писем = 0
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    р = z.get("по_видам")
    if not isinstance(р, dict) or not р:
        continue
    писем += 1
    всего += int(z.get("вызовов") or 0)
    исходы["ок" if z.get("ок") else "брак"] += 1
    for k, v in р.items():
        виды[k] += int(v)
        if z.get("ок"):
            для_ок[k] += int(v)
    if z.get("ок"):
        ок_писем += 1

print(f"писем с разбивкой: {писем} (ок {исходы['ок']}, брак {исходы['брак']})")
if not писем:
    print("разбивки пока нет — прогон ещё идёт")
    raise SystemExit(0)
print(f"вызовов всего: {всего}, на письмо {всего/писем:.1f}\n")
имена = {"gen": "генерация письма (opus)", "jdg": "судья выбора варианта",
         "vf": "верификатор правил", "teh": "техлинза (технолог+скептик)",
         "fix": "починка"}
print(f"{'вид':<34} {'вызовов':>8} {'на письмо':>10}")
for k, n in виды.most_common():
    корень = next((и for и in имена if k.startswith(и)), k)
    print(f"  {имена.get(корень, k):<32} {n:>8} {n/писем:>10.1f}")
if ок_писем:
    print(f"\nтолько по удачным ({ок_писем} писем):")
    for k, n in для_ок.most_common():
        корень = next((и for и in имена if k.startswith(и)), k)
        print(f"  {имена.get(корень, k):<32} {n:>8} {n/ок_писем:>10.1f}")
