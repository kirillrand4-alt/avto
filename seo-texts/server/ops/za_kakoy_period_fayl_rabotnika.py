# -*- coding: utf-8 -*-
"""За какой период файл работника: не обрезан ли он (тогда «не видел» ≠ «не проверял»)."""
import io
import json
from collections import Counter

Ф = r"C:\sender\_ops\probe-rezultat.jsonl"
дни = Counter()
всего = 0
for s in io.open(Ф, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    всего += 1
    дни[str(z.get("ts") or z.get("время") or "")[:10]] += 1
print(f"строк: {всего}")
for d, n in sorted(дни.items()):
    print(f"  {d}  {n}")
