# -*- coding: utf-8 -*-
"""Претензия рецензента целиком по названным id — без обрезки."""
import io
import json
import sys

ЖУРНАЛ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ИДЫ = {int(a) for a in sys.argv[1:] if a.isdigit()}
верд = {}
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = z
    except Exception:                                            # noqa: BLE001
        pass
for i in sorted(ИДЫ):
    z = верд.get(i) or {}
    пр = z.get("pretenzii") or []
    if isinstance(пр, str):
        пр = [пр]
    print(f"#{i} {str(z.get('фирма') or '')[:44]} — {z.get('url')}")
    for p in пр:
        print(f"   · {p}")
