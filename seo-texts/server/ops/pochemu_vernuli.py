# -*- coding: utf-8 -*-
"""Почему пересуд вернул именно этих: причины по журналу."""
import io
import json
import sys

Ж = r"C:\sender\_ops\peresud-geyta.jsonl"
ИНН = {a for a in sys.argv[1:] if a.isdigit()}
for s in io.open(Ж, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if ИНН and str(z.get("inn")) not in ИНН:
        continue
    if not ИНН and z.get("стало") == "не покупатель":
        continue
    print(f"{z.get('inn')}  {str(z.get('имя'))[:38]:<38} -> {z.get('стало')}")
    print(f"    {str(z.get('почему'))[:220]}")
