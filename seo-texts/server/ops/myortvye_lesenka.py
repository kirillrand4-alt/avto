# -*- coding: utf-8 -*-
"""Компании списка КЦ-1, у которых основной адрес мёртв по пробе: что с их
следующими адресами по лесенке (enrich.emails) — проверены ли, живые ли, на
своём ли домене. Только чтение."""
import io
import json
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
сч, итог = Counter(), Counter()
for rid, inn, em, ex in c.execute("SELECT id, inn, lower(email), extra_json FROM recipients WHERE extra_json LIKE '%КЦ-1%'"):
    if проба.get(em) not in ("нет ящика", "нет MX"):
        continue
    сайт = str((e.execute("SELECT site FROM companies WHERE inn=?", (str(inn),)).fetchone() or [""])[0] or "").lower()
    сайт = сайт.split("//")[-1].split("/")[0].replace("www.", "")
    вид = Counter()
    for a, роль in e.execute("SELECT lower(email), role FROM emails WHERE inn=? AND lower(email)!=?", (str(inn), em)):
        if "не для письма" in str(роль or "").lower():
            continue
        свой = сайт and (a.endswith("@" + сайт) or a.endswith("." + сайт))
        вид[(проба.get(a) or "не проверен", "свой домен" if свой else "чужой/публичный")] += 1
    итог["компаний с мёртвым основным"] += 1
    if not вид:
        итог["запасных нет вовсе"] += 1
    elif any(k[0] in ("есть", "принимает всё") and k[1] == "свой домен" for k in вид):
        итог["есть живой запасной на своём домене"] += 1
    elif any(k[0] in ("есть", "принимает всё") for k in вид):
        итог["живой запасной только на чужом/публичном домене"] += 1
    elif any(k[0] == "не проверен" for k in вид):
        итог["запасные есть, но НЕ проверены"] += 1
    else:
        итог["все запасные мертвы/неясны"] += 1
    сч.update(вид)
for k, v in итог.most_common():
    print("  %-48s %4d" % (k, v))
print("запасные адреса по виду:", сч.most_common(8))
