# -*- coding: utf-8 -*-
"""Что вышло из переписывания: было -> стало, с претензией рецензента."""
import io
import json
import re
import sys

Ж = r"C:\sender\_ops\perepisano-po-recenzii.jsonl"
N = int(next((a for a in sys.argv[1:] if a.isdigit()), "2"))
итог_фильтр = next((a for a in sys.argv[1:] if not a.isdigit()), "годно")

строки = []
for s in io.open(Ж, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                             # noqa: BLE001
        continue
    if итог_фильтр in str(z.get("итог") or ""):
        строки.append(z)
print(f"(записей «{итог_фильтр}»: {len(строки)}, печатаю {min(N,len(строки))})")
for z in строки[:N]:
    print(f"\n{'='*70}\n#{z['id']}  {z.get('итог')}\n{'='*70}")
    if z.get("pretenzii"):
        print("ПРЕТЕНЗИИ ПОСЛЕ ПРАВКИ:",
              "; ".join(str(x) for x in z["pretenzii"])[:300])
    if z.get("брак"):
        print("ГЕЙТ:", "; ".join(str(x) for x in z["брак"])[:300])
    if z.get("было"):
        print(f"\n--- БЫЛО (начало) ---\n{z['было'][:400]}")
    print(f"\n--- СТАЛО ---\nТЕМА: {z.get('тема')}\n{z.get('тело')}")
