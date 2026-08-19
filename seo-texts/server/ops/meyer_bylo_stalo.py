# -*- coding: utf-8 -*-
"""Мейеровские письма до и после перезаписи по новым правилам."""
import io
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

Ж = r"C:\sender\_ops\peregeneraciya-meyer.jsonl"
СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "2"))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

ок = []
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("ок"):
        ок.append(z)
print(f"переписанных в журнале: {len(ок)}; показываю {СКОЛЬКО}")
шаг = max(1, len(ок) // max(1, СКОЛЬКО))
for z in [ок[i] for i in range(0, len(ок), шаг)][:СКОЛЬКО]:
    строка = store.confirm_get(int(z["id"])) or {}
    print("\n" + "=" * 72)
    print(f"#{z['id']}  {z.get('фирма')}")
    print("-" * 72)
    print("БЫЛО:")
    print(f"ТЕМА: {z.get('тема_до')}\n\n{(z.get('тело_до') or '')[:1400]}")
    print("-" * 72)
    print("СТАЛО:")
    print(f"ТЕМА: {строка.get('subject')}\n\n{(строка.get('body') or '')[:1400]}")
