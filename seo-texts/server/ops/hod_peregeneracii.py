# -*- coding: utf-8 -*-
"""Ход перегенерации по durable-журналу на сервере."""
import io
import json
import os
from collections import Counter
Ж = r"C:\sender\_ops\peregeneraciya-braka.jsonl"
if not os.path.exists(Ж):
    print("журнала ещё нет")
    raise SystemExit(0)
c = Counter()
последние = []
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    c["ок" if z.get("ок") else f"не ок: {str(z.get('почему'))[:50]}"] += 1
    последние.append(z.get("id"))
print(f"записей в журнале: {sum(c.values())}")
for k, n in c.most_common(8):
    print(f"  {n:>4}  {k}")
print("последние id:", последние[-8:])
