# -*- coding: utf-8 -*-
"""Проверка журнала генерации (по умолчанию закупщики КЦ): отсев по причинам, письма с подозрительной
фразой (общей/пустой/латиница/цифры/повтор), каждое 20-е — фразой. proverka_zhurnala_pisem.py [журнал]"""
import collections, io, json, re, sys
п = sys.argv[1] if len(sys.argv) > 1 else r"C:\sender\_ops\zakupshchiki-kc.jsonl"
з = [json.loads(s) for s in io.open(п, encoding="utf-8")]
от = collections.Counter(); подозр = []; фразы = collections.Counter(); ок = []
for x in з:
    if x.get("otsev"):
        от[re.sub(r"\d{6,}|'.*", "", x["otsev"])[:50]] += 1; continue
    ок.append(x)
    ф = x["telo"].split("\n\n")[1].split(". ")[0]
    фразы[ф] += 1
    if re.search(r"технологическ|может применяться|^На производстве |[A-Za-z]{4,}|\d|  |\.\.", ф) or len(ф) < 40:
        подозр.append((x["karta"], x["email"], ф[:170]))
print("писем: %d | отсев: %s" % (len(ок), dict(от)))
print("повторов одной и той же фразы (>1):", sum(1 for v in фразы.values() if v > 1))
print("подозрительных: %d" % len(подозр))
for p in подозр[:25]: print("  #%s %s | %s" % p)
if "--kazhdoe20" in sys.argv:
    for x in ок[::20]:
        print("  #%s %s | %s" % (x["karta"], x["email"], x["telo"].split("\n\n")[1].split(". ")[0][:150]))
