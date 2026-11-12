# -*- coding: utf-8 -*-
"""Хвост лога и итог журнала перепробы (только чтение)."""
import io, json, os
from collections import Counter
print("".join(io.open(r"C:\sender\_ops\gaz-pereproba-neyasnyh.log", encoding="utf-8", errors="replace").readlines()[-6:]))
ж = r"C:\sender\_ops\gaz-pereproba-neyasnyh.jsonl"
if os.path.exists(ж):
    з = [json.loads(с) for с in io.open(ж, encoding="utf-8")]
    print("в журнале:", len(з), dict(Counter(x["itog"] for x in з)))
    print("возвраты:", dict(Counter(x.get("vozvrat", "") for x in з if x.get("vozvrat"))))
    print("ответы «неясно»:", Counter(x.get("otvet", "")[:70] for x in з if x["itog"] == "неясно").most_common(8))
