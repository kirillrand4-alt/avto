# -*- coding: utf-8 -*-
"""Свод линз кампании 23 (последняя запись на карточку): инженерная (ok / с исправлением / газ не нужен) и адресат.
Только чтение."""
import io, json, sqlite3
from collections import Counter
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
pend = {r[0] for r in c.execute("SELECT id FROM confirm_reviews WHERE campaign_id=23 AND status='pending'")}
def посл(имя):
    д = {}
    for с in io.open(r"C:\sender\_ops\%s.jsonl" % имя, encoding="utf-8"):
        try: з = json.loads(с); д[з["karta"]] = з
        except (ValueError, KeyError): pass
    return {к: з for к, з in д.items() if к in pend}
и = посл("gaz-kc-linza-23"); а = посл("gaz-kc-adresat-23")
print("pending:", len(pend), "| инженерная проверила:", len(и), "| адресат проверил:", len(а))
print("инженерная:", Counter("ok" if з.get("ok") else ("есть исправление" if (з.get("fix") or "").strip() else "газ не нужен") for з in и.values()))
print("адресат:", Counter("ok" if з.get("ok") else "мимо" for з in а.values()))
оба = [к for к in pend if к in и and к in а and not и[к].get("ok") and not (и[к].get("fix") or "").strip() and not а[к].get("ok")]
print("и газ не нужен, и мимо адресата:", len(оба))
print("примеры замечаний адресата:", [str(з.get("problem") or з.get("pochemu") or "")[:110] for з in list(а.values()) if not з.get("ok")][:5])
