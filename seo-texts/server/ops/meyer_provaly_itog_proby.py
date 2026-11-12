# -*- coding: utf-8 -*-
"""Итог пробы по КОМПАНИЯМ meyer-provaly2.jsonl: у компании есть живой адрес (есть) / только «принимает всё» /
все мёртвы / только неясные. Плюс в разрезе Продажа/Привлечение и чистых (без стопа и письма за 60 дней). Только чтение."""
import io, json
from collections import Counter
в = {}
for с in io.open(r"C:\sender\_ops\proba-meyer-provaly.jsonl", encoding="utf-8"):
    x = json.loads(с); в[x["email"]] = x["itog"]
сч, чист, прод = Counter(), Counter(), Counter()
for с in io.open(r"C:\sender\_ops\meyer-provaly2.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if x.get("stop"): сч["стоп-лист"] += 1; continue
    вер = [в.get(e.strip().lower(), "не проверен") for e in x["emails"]]
    к = ("есть живой адрес" if "есть" in вер else "только «принимает всё»" if "принимает всё" in вер
         else "все мёртвы" if вер and all(v in ("нет ящика", "нет MX") for v in вер) else "только неясные/отказ пробе")
    сч[к] += 1
    if not x.get("pisali60"): чист[к] += 1
    if x.get("prodazha"): прод[к] += 1
print("компании:", dict(сч)); print("чистые (без письма на тот же адрес за 60 дн):", dict(чист)); print("с провалом в Продаже:", dict(прод))
