# -*- coding: utf-8 -*-
"""Какие поля пишет рецензент — чтобы читать претензию из правильного."""
import io
import json
from collections import Counter

ключи = Counter()
примеры = {}
n = 0
for s in io.open(r"C:\sender\_ops\rezenzii-pisem.jsonl", encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                             # noqa: BLE001
        continue
    n += 1
    for k, v in z.items():
        ключи[k] += 1
        if k not in примеры and v not in (None, "", [], {}):
            примеры[k] = json.dumps(v, ensure_ascii=False)[:130]
print(f"строк: {n}")
for k, c in ключи.most_common():
    print(f"  {c:>6}  {k:<16} {примеры.get(k,'')}")
