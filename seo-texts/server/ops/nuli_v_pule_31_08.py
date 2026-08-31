# -*- coding: utf-8 -*-
"""Только чтение: сколько нулей (=нет данных) в мейеровском пуле."""
import json
import sqlite3
from collections import Counter

СУТЬ = {"продукция", "упаковка_фасовка", "сырьё", "мощности", "контроль_качества",
        "экспорт", "оборудование_линии", "клиенты", "год_основания",
        "география_поставок", "масштаб", "расширение", "газы", "энергохозяйство",
        "новости"}
ПОРОГ = 30_000_000


def непусто(v):
    return v not in (None, "", [], {}, "нет")


def норм(d):
    d = str(d or "").strip().lower()
    for п in ("https://", "http://"):
        if d.startswith(п):
            d = d[len(п):]
    d = d.split("/")[0].split("?")[0].split(":")[0]
    return (d[4:] if d.startswith("www.") else d).strip(". ")


e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

пасп = {}
for р in e.execute("SELECT inn, facts_json, site FROM site_facts"):
    try:
        f = json.loads(р["facts_json"] or "{}")
    except Exception:
        continue
    пасп[str(р["inn"])] = (норм(р["site"]),
                           sum(1 for k, v in f.items() if k in СУТЬ and непусто(v)))
выр = {}
for р in e.execute("SELECT inn, revenue_rub FROM companies"):
    try:
        выр[str(р["inn"])] = None if р["revenue_rub"] is None else float(р["revenue_rub"])
    except Exception:
        выр[str(р["inn"])] = None
ист = {}
for таб, кол in (("emails", "source_url"), ("email_sources", "url")):
    for р in e.execute("SELECT inn, email, %s u FROM %s" % (кол, таб)):
        d = норм(р["u"])
        if d:
            ист.setdefault((str(р["inn"]), str(р["email"] or "").lower()), set()).add(d)

инн_пула = set()
for р in s.execute("SELECT inn, email, domain FROM recipients WHERE segment='meyer'"):
    i, em, dom = str(р["inn"] or ""), str(р["email"] or "").lower(), норм(р["domain"])
    p = пасп.get(i)
    if not p or p[1] < 1:
        continue
    сайт = p[0]
    if сайт and (dom == сайт or сайт in ист.get((i, em), set())):
        инн_пула.add(i)

к = Counter()
for i in инн_пула:
    v = выр.get(i, None)
    if v is None:
        к["нет записи / NULL"] += 1
    elif v == 0:
        к["РОВНО 0 (скорее нет данных)"] += 1
    elif v >= ПОРОГ:
        к["30 млн и выше"] += 1
    else:
        к["больше 0, но меньше 30 млн"] += 1

print("=== ПУЛ: паспорт с фактом + почта, %d компаний ===" % len(инн_пула))
for k, v in к.most_common():
    print("  %-32s %5d (%4.1f%%)" % (k, v, 100.0 * v / max(1, len(инн_пула))))

неизв = к["нет записи / NULL"] + к["РОВНО 0 (скорее нет данных)"]
print("\n=== ИТОГ ===")
print("  ТОЧНО подходит (>= 30 млн)            : %d" % к["30 млн и выше"])
print("  ТОЧНО не подходит (0 < выручка < 30)  : %d" % к["больше 0, но меньше 30 млн"])
print("  НЕИЗВЕСТНА (ноль или пусто)           : %d (%.0f%%)"
      % (неизв, 100.0 * неизв / max(1, len(инн_пула))))
print("  по критерию «>=30 млн ЛИБО неизвестна»: %d"
      % (к["30 млн и выше"] + неизв))
