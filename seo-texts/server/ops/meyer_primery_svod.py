# -*- coding: utf-8 -*-
"""Короткий свод банка примеров Meyer: группа | вид | станок | компаний | годных/всего; --frazy — фразы с вердиктами.
    meyer_primery_svod.py [--frazy] [--ot=N] [--do=M]   Только чтение."""
import io, json, sys
from collections import Counter
О = r"C:\sender\_ops"
пр = [json.loads(с) for с in io.open(О + r"\meyer-primery.jsonl", encoding="utf-8")]
гр = json.load(io.open(О + r"\meyer-gruppy.json", encoding="utf-8"))
покр = Counter()
for с in io.open(О + r"\meyer-produkt-gruppa.jsonl", encoding="utf-8"):
    з = json.loads(с); покр[з["gruppa"]] += з["kompaniy"]
ot = int(next((a[5:] for a in sys.argv if a.startswith("--ot=")), 0)); do = int(next((a[5:] for a in sys.argv if a.startswith("--do=")), 999))
for i, г in enumerate(гр):
    if not ot <= i < do: continue
    фф = [з for з in пр if з["gruppa"] == г["imya"]]
    print("%d. %s | %s | %s | комп %d | годных %d/%d" % (i, г["imya"], г.get("vid"), г.get("stanok"), покр.get(г["imya"], 0), sum(з["godna"] for з in фф), len(фф)))
    if "--frazy" in sys.argv:
        for з in фф:
            print("   %s %s" % ("+" if з["godna"] else "-", з["fraza"]))
            if not з["godna"]:
                for к in ("tehnolog", "skeptik"):
                    if з[к].get("verdict") != "верно": print("      %s: %s" % (к, з[к].get("pochemu", "")[:220]))
print("без группы: %d" % покр.get("нет", 0))
