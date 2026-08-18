# -*- coding: utf-8 -*-
"""Как устроена запись журнала рецензий — чтобы считать причины, а не гадать."""
import io
import json
from collections import Counter

ж = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ключи = Counter()
примеры = {}
не_годно = []
for s in io.open(ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    for k, v in z.items():
        ключи[k] += 1
        примеры.setdefault(k, v)
    if str(z.get("вердикт") or z.get("verdict") or "") == "не годно":
        не_годно.append(z)

print("ключи записи:")
for k, n in ключи.most_common():
    о = примеры.get(k)
    print(f"  {k:<20} {n:>5}   пример: {str(о)[:90]}")
print(f"\nзаписей «не годно»: {len(не_годно)}")
for z in не_годно[:5]:
    print("  ---")
    print("  " + json.dumps(z, ensure_ascii=False)[:600])
