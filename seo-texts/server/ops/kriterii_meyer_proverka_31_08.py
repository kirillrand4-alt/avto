# -*- coding: utf-8 -*-
"""Только чтение: разложить критерий 2 и проверить набор «уже писали»."""
import json
import sqlite3
from collections import Counter

ПОРОГ = 30_000_000


def норм(d):
    d = str(d or "").strip().lower()
    for п in ("https://", "http://"):
        if d.startswith(п):
            d = d[len(п):]
    d = d.split("/")[0].split("?")[0].split(":")[0]
    if d.startswith("www."):
        d = d[4:]
    return d.strip(". ")


e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

паспорт = {}
for р in e.execute("SELECT inn, facts_json, site FROM site_facts"):
    try:
        f = json.loads(р["facts_json"] or "{}")
    except Exception:
        continue
    b = sum(1 for v in f.values() if v not in (None, "", [], {}, "нет"))
    if b:
        паспорт[str(р["inn"])] = (норм(р["site"]), b)
выручка = {}
for р in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL"):
    try:
        выручка[str(р["inn"])] = float(р["revenue_rub"])
    except Exception:
        pass
источник = {}
for таб, кол in (("emails", "source_url"), ("email_sources", "url")):
    for р in e.execute("SELECT inn, email, %s u FROM %s" % (кол, таб)):
        d = норм(р["u"])
        if d:
            источник.setdefault((str(р["inn"]), str(р["email"] or "").lower()), set()).add(d)

print("=== «уже писали»: по таблицам ===")
писали = set()
for таб in ("ai_letter_log", "confirm_reviews"):
    try:
        n0 = len(писали)
        for р in s.execute("SELECT DISTINCT inn FROM %s WHERE inn IS NOT NULL" % таб):
            писали.add(str(р["inn"]))
        print("  %-18s дало ИНН: всего стало %d (+%d)" % (таб, len(писали), len(писали) - n0))
    except Exception as ex:
        print("  %-18s ОШИБКА: %s" % (таб, str(ex)[:60]))

# группа «Партия 935»
в_935 = set()
try:
    гр = s.execute("SELECT id, extra_json FROM recipients WHERE extra_json LIKE '%935%'")
    for р in гр:
        в_935.add(р["id"])
except Exception as ex:
    print("  группа: %s" % str(ex)[:60])

ш = Counter()
инн = set()
инн_935 = set()
for р in s.execute("SELECT id, inn, email, domain FROM recipients WHERE segment='meyer'"):
    i, em, dom = str(р["inn"] or ""), str(р["email"] or "").lower(), норм(р["domain"])
    p = паспорт.get(i)
    if not p:
        continue
    сайт, b = p
    совпал = bool(сайт) and dom == сайт
    с_сайта = сайт in источник.get((i, em), set()) if сайт else False
    if совпал and с_сайта:
        ш["и домен совпал, и почта с сайта"] += 1
    elif совпал:
        ш["только домен совпал"] += 1
    elif с_сайта:
        ш["только почта с сайта (домен другой)"] += 1
    else:
        ш["ни то ни другое (отсеян)"] += 1
        continue
    v = выручка.get(i)
    if v is not None and v >= ПОРОГ:
        инн.add(i)
        if р["id"] in в_935:
            инн_935.add(i)

print("\n=== КРИТЕРИЙ 2 В РАЗБИВКЕ ===")
for k, v in ш.most_common():
    print("  %-38s %6d" % (k, v))

print("\n=== ИТОГ ===")
print("  компаний, прошедших все три критерия: %d" % len(инн))
print("  из них ещё не писали                : %d" % len({x for x in инн if x not in писали}))
print("  из них в группе «Партия 935»         : %d" % len(инн_935))
print("  ИНН в наборе «уже писали»            : %d" % len(писали))
