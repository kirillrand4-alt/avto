# -*- coding: utf-8 -*-
"""Ход пробы списка: хвост лога и итог журнала.  hvost_proby_spiska.py [имя=meyer-provaly]"""
import io, json, os, sys
from collections import Counter
и = sys.argv[1] if len(sys.argv) > 1 else "meyer-provaly"
print("".join(io.open(r"C:\sender\_ops\proba-%s.log" % и, encoding="utf-8", errors="replace").readlines()[-4:]))
ж = r"C:\sender\_ops\proba-%s.jsonl" % и
if os.path.exists(ж):
    з = {}
    for с in io.open(ж, encoding="utf-8"): x = json.loads(с); з[x["email"]] = x
    print("адресов:", len(з), dict(Counter(x["itog"] for x in з.values())))
    print("неясно:", Counter(str(x.get("otvet", ""))[:60] for x in з.values() if x["itog"] == "неясно").most_common(6))
