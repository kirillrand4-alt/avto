# -*- coding: utf-8 -*-
"""Сверка компаний по ЕГРЮЛ (dadata findById): название, регион, ОКВЭД, статус,
руководитель, выручка (finance, если есть). Только чтение.
    dadata_proverka.py ИНН,ИНН,...  [поиск названия: --imya="Непецино"]"""
import json
import sys
import urllib.request
sys.path.insert(0, r"C:\sender\server")
import enrich_contacts as EC  # noqa: E402
tok = EC._read_secret("DADATA_TOKEN")


def zapros(путь, тело):
    req = urllib.request.Request("https://suggestions.dadata.ru/suggestions/api/4_1/rs/" + путь,
                                 data=json.dumps(тело).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json", "Authorization": "Token " + tok})
    return json.loads(urllib.request.urlopen(req, timeout=25).read()).get("suggestions") or []


for инн in [x for x in sys.argv[1].split(",") if x]:
    р = zapros("findById/party", {"query": инн})
    if not р:
        print("%s: НЕТ В ЕГРЮЛ" % инн)
        continue
    d = р[0].get("data") or {}
    фин = d.get("finance") or {}
    print("%s: %s | %s | ОКВЭД %s | %s | рук.: %s | выручка %s (год %s)" % (
        инн, р[0].get("value"), ((d.get("address") or {}).get("data") or {}).get("region_with_type"), d.get("okved"),
        ((d.get("state") or {}).get("status")), ((d.get("management") or {}).get("name")), фин.get("income") or фин.get("revenue"), фин.get("year")))
for a in sys.argv[2:]:
    if a.startswith("--imya="):
        for s in zapros("suggest/party", {"query": a.split("=", 1)[1], "count": 5}):
            d = s.get("data") or {}
            print("поиск: %s | ИНН %s | %s" % (s.get("value"), d.get("inn"), ((d.get("address") or {}).get("data") or {}).get("region_with_type")))
