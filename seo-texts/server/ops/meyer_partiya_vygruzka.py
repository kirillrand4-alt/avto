# -*- coding: utf-8 -*-
"""Выгрузка партии «провалы Meyer» владельцу на вычитку: случайные письма «ок» по шаблонам и все отсеянные
(«не писать» / «ошибка») с причиной. Пишет _ops/meyer-vygruzka.json. Только чтение журнала.  [--na-shablon=6]"""
import io, json, random, sys
N = int(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--na-shablon=")), "6"))
зз = [json.loads(с) for с in io.open(r"C:\sender\_ops\meyer-partiya.jsonl", encoding="utf-8")]
random.seed(1711)
пис = []
for ш in ("KUPILI", "NET_ZADACH", "OTLOZHILI"):
    ок = [з for з in зз if з["shablon"] == ш and з["status"] == "ок"]
    for з in random.sample(ок, min(N, len(ок))):
        пис.append({"sh": ш, "komp": з.get("kompaniya") or "", "tema": з["tema"], "pismo": з["pismo"], "perefraz": з.get("perefraz")})
отс = []
for з in зз:
    if з["status"] == "ок": continue
    пр = "; ".join("%s: %s" % (к, (з.get(к, {}).get("pochemu") or "")[:140]) for к in ("tehnolog", "skeptik", "redaktor")
                   if з.get(к, {}).get("verdict") == "ошибка")
    отс.append({"st": з["status"], "sh": з["shablon"], "komp": (з.get("kompaniya") or "")[:70], "pr": пр or "модель: не писать (не наш клиент / задача не наша)"})
json.dump({"pisma": пис, "otseyannye": отс}, io.open(r"C:\sender\_ops\meyer-vygruzka.json", "w", encoding="utf-8"), ensure_ascii=False)
from collections import Counter
print("писем:", len(пис), "отсеяно:", len(отс), dict(Counter(з["status"] for з in зз)))
