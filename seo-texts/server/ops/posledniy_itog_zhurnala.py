# -*- coding: utf-8 -*-
"""Последняя запись «итог» в журнале партии: куда легло письмо."""
import io
import json

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
строки = []
for s in io.open(Ж, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "итог":
        строки.append(z)
for z in строки[-2:]:
    print("=" * 70)
    for k in ("inn", "имя", "направление", "ок", "брак", "review_id",
              "статус_очереди", "цена_$", "вызовов", "сек", "модель",
              "панель_упала"):
        if k in z:
            print(f"  {k}: {str(z[k])[:150]}")
