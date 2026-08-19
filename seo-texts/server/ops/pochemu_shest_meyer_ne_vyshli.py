# -*- coding: utf-8 -*-
"""Почему шесть мейеровских писем не переписались с трёх попыток.

Они остаются в очереди со старым текстом. Перед тем как махнуть рукой,
надо назвать причину поимённо: если это претензия к адресату, письмо надо
снимать, а не переписывать.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

Ж = r"C:\sender\_ops\peregeneraciya-meyer.jsonl"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

последние = {}
успех = set()
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    i = int(z["id"])
    if z.get("ок"):
        успех.add(i)
    последние[i] = z
причины = Counter()
for i, z in последние.items():
    if i in успех:
        continue
    row = store.confirm_get(i) or {}
    if row.get("status") != "pending":
        continue
    ф = z.get("fails") or []
    имя = row.get("company_name") or z.get("фирма") or i
    print(f"\n#{i}  {str(имя)[:44]}")
    print(f"  почему: {str(z.get('почему'))[:100]}")
    for x in ф[:4]:
        print(f"    - {str(x)[:110]}")
        причины[str(x).split(':')[0][:40]] += 1
print("\nсводка причин:")
for k, n in причины.most_common(8):
    print(f"  {n:>3}  {k}")
