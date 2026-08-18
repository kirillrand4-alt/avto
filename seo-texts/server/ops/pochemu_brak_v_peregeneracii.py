# -*- coding: utf-8 -*-
"""Почему письма уходят в брак при перегенерации — старым и новым конвейером.

Дешёвая проверка, которая чаще бракует, дороже дорогой: каждый брак стоит
полного круга заново. Сравниваем долю брака и причины у записей со счётчиком
вызовов (новый конвейер) и без него (старый).
"""
import io
import json
from collections import Counter

Ж = r"C:\sender\_ops\peregeneraciya-braka.jsonl"
стар = Counter()
нов = Counter()
причины_нов = Counter()
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    новый = isinstance(z.get("по_видам"), dict) and z["по_видам"]
    куда = нов if новый else стар
    куда["ок" if z.get("ок") else "брак"] += 1
    if новый and not z.get("ок"):
        for f in (z.get("fails") or [])[:3]:
            причины_нов[str(f)[:70]] += 1
        if not z.get("fails"):
            причины_нов[str(z.get("почему"))[:70]] += 1


def _доля(c, имя):
    n = sum(c.values())
    if not n:
        print(f"{имя}: записей нет")
        return
    print(f"{имя}: {n} писем, брак {c['брак']} = {100.0*c['брак']/n:.0f}%")


_доля(стар, "старый конвейер (opus на всём, две линзы, 3 варианта)")
_доля(нов, "новый конвейер (проверки sonnet, одна линза, 2 варианта)")
if причины_нов:
    print("\nпричины брака у нового конвейера:")
    for п, n in причины_нов.most_common(12):
        print(f"  {n:>3}  {п}")
