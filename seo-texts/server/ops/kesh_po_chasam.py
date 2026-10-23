# -*- coding: utf-8 -*-
"""Цена письма и кэш провайдера по часам (журнал генерации): запись/чтение
кэша на попытку, $ на попытку. kesh_po_chasam.py <журнал>"""
import io
import json
import sys
from collections import defaultdict

д = defaultdict(lambda: [0, 0, 0, 0.0])
for s in io.open(sys.argv[1], encoding="utf-8"):
    try:
        z = json.loads(s)
    except ValueError:
        continue
    if "цена_$" not in z:
        continue
    ч = str(z.get("ts") or z.get("время") or "")[:13] or "?"
    к = д[(z.get("день"), ч)]
    к[0] += 1
    к[1] += int(z.get("вход_кэш_запись") or 0)
    к[2] += int(z.get("вход_кэш_чтение") or 0)
    к[3] += float(z.get("цена_$") or 0)
for k, (n, w, r, usd) in sorted(д.items(), key=lambda x: str(x[0])):
    print(k, "попыток %d | кэш запись %dк, чтение %dк на попытку | $%.3f на попытку" % (n, w / n / 1000, r / n / 1000, usd / n))
