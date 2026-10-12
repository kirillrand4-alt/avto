# -*- coding: utf-8 -*-
"""Цена всех писем «Россия 9000» за день по журналу драйвера (без дублей)."""
import io
import json
from collections import OrderedDict
по = OrderedDict()
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if z.get("цена_$") is None:
        continue
    по[(z.get("recipient_id"), z.get("создана") or z.get("день"))] = z
попыток = len(по)
годных = sum(1 for z in по.values() if z.get("тело"))
цена = sum(float(z.get("цена_$") or 0) for z in по.values())
письмо = sum(float(z.get("цена_письма_$") or 0) for z in по.values())
пров = sum(float(z.get("цена_проверок_$") or 0) for z in по.values())
print("попыток %d, годных %d (%.0f%%), брак %d" % (попыток, годных,
      100.0 * годных / max(1, попыток), попыток - годных))
print("потрачено $%.2f (письмо $%.2f + проверки $%.2f)" % (цена, письмо, пров))
print("за попытку $%.3f, ЗА ГОДНОЕ ПИСЬМО $%.3f" % (цена / max(1, попыток),
                                                   цена / max(1, годных)))
print("=== ЦЕНА ЗА ДЕНЬ ===")
