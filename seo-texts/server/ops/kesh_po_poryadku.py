# -*- coding: utf-8 -*-
"""Кэш и цена попытки по порядку записей журнала генерации (окнами по N):
когда подорожало. kesh_po_poryadku.py <журнал> [N=40]"""
import io
import json
import sys

N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
ряды = []
for s in io.open(sys.argv[1], encoding="utf-8"):
    try:
        z = json.loads(s)
    except ValueError:
        continue
    if "цена_$" in z:
        ряды.append(z)
for i in range(0, len(ряды), N):
    к = ряды[i:i + N]
    n = len(к)
    w = sum(int(z.get("вход_кэш_запись") or 0) for z in к) / n / 1000
    r = sum(int(z.get("вход_кэш_чтение") or 0) for z in к) / n / 1000
    вх = sum(int(z.get("вход") or z.get("вход_токены") or 0) for z in к) / n / 1000
    usd = sum(float(z.get("цена_$") or 0) for z in к) / n
    пр = sum(float(z.get("цена_проверок_$") or 0) for z in к) / n
    print("%5d-%5d | кэш запись %5.1fк чтение %5.1fк вход %5.1fк | $%.3f (проверки $%.3f) | %s" % (
        i, i + n, w, r, вх, usd, пр, к[-1].get("модель")))
print("ключи записи:", sorted(ряды[-1].keys()) if ряды else "-")
