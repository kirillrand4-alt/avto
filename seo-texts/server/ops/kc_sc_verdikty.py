# -*- coding: utf-8 -*-
"""Вердикты пробы у выбранных адресов партии КЦ СЦ (kc-sc-lesenka.jsonl) и у заведённых карточек (kc-sc-sdelki2). Только чтение."""
import io, json
from collections import Counter
лес = {}
for с in io.open(r"C:\sender\_ops\kc-sc-lesenka.jsonl", encoding="utf-8"):
    x = json.loads(с); лес[x["kluch"]] = x
print("лесенка:", dict(Counter(x.get("status") for x in лес.values())), "| вердикты выбранных:", dict(Counter(x.get("verdict") for x in лес.values() if x.get("status") == "выбран")))
к = {}
for с in io.open(r"C:\sender\_ops\kc-sc-sdelki2-kartochki.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if x.get("karta"): к[x["kluch"]] = x
print("карточек %d, вердикты их адресов: %s" % (len(к), dict(Counter(лес.get(k, {}).get("verdict") for k in к))))
