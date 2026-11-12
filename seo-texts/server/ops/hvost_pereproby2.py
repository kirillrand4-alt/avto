# -*- coding: utf-8 -*-
"""Хвост лога и итог журнала второго захода перепробы (только чтение)."""
import io, json, os
from collections import Counter
print("".join(io.open(r"C:\sender\_ops\gaz-pereproba2.log", encoding="utf-8", errors="replace").readlines()[-5:]))
ж = r"C:\sender\_ops\gaz-pereproba2.jsonl"
if os.path.exists(ж):
    з = {}
    for с in io.open(ж, encoding="utf-8"): x = json.loads(с); з[x["email"]] = x
    print("адресов:", len(з), dict(Counter(x["itog"] for x in з.values())))
    print("возвраты:", dict(Counter(x.get("vozvrat", "") for x in з.values() if x.get("vozvrat"))))
    print("неясно:", Counter(str(x.get("otvet", ""))[:70] for x in з.values() if x["itog"] == "неясно").most_common(10))
