# -*- coding: utf-8 -*-
"""Итог журнала генерации с момента ts: zhurnal_itog_s.py <журнал.jsonl> <ts-ISO>"""
import io, json, sys, collections
п, с = sys.argv[1], sys.argv[2]
c = collections.Counter(); примеры = collections.defaultdict(list)
for l in io.open(п, encoding="utf-8"):
    try: d = json.loads(l)
    except Exception: continue
    if d.get("ts", "") < с: continue
    o = d.get("otsev", "")
    k = (o.split(":")[0].split(" %")[0][:30] if o else ("заведено, общая почта группы" if d.get("gruppa_obshchiy") else "заведено"))
    c[k] += 1
    if len(примеры[k]) < 3 and k.startswith("адрес"): примеры[k].append(o)
for k, v in c.most_common(): print(v, k)
for k, v in примеры.items(): print(k, v)
