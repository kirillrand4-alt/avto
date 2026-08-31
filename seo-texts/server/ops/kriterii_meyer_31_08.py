# -*- coding: utf-8 -*-
"""Только чтение. Три критерия владельца по Meyer:
   1) есть паспорт сайта (непустые блоки в site_facts.facts_json)
   2) почта с сайта паспорта ИЛИ её домен совпадает с доменом паспорта
   3) выручка >= 30 млн руб.
Ничего не меняет."""
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

# 1. паспорта
паспорт = {}
for р in e.execute("SELECT inn, facts_json, site FROM site_facts"):
    try:
        f = json.loads(р["facts_json"] or "{}")
    except Exception:
        continue
    блоков = sum(1 for v in f.values() if v not in (None, "", [], {}, "нет"))
    if блоков:
        паспорт[str(р["inn"])] = (норм(р["site"]), блоков)
print("паспортов с непустыми блоками: %d" % len(паспорт))

# 2. выручка
выручка = {}
for р in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL"):
    try:
        выручка[str(р["inn"])] = float(р["revenue_rub"])
    except Exception:
        pass
print("компаний с выручкой: %d (>=30млн: %d)"
      % (len(выручка), sum(1 for v in выручка.values() if v >= ПОРОГ)))

# 3. откуда взята почта
источник = {}
for таб, кол in (("emails", "source_url"), ("email_sources", "url")):
    try:
        for р in e.execute("SELECT inn, email, %s u FROM %s" % (кол, таб)):
            d = норм(р["u"])
            if d:
                источник.setdefault((str(р["inn"]), str(р["email"] or "").lower()),
                                    set()).add(d)
    except Exception as ex:
        print("  %s: %s" % (таб, str(ex)[:60]))
print("пар (инн,почта) с известным источником: %d" % len(источник))

# уже писали
писали = set()
for таб in ("ai_letter_log", "confirm_reviews"):
    try:
        for р in s.execute("SELECT DISTINCT inn FROM %s WHERE inn IS NOT NULL" % таб):
            писали.add(str(р["inn"]))
    except Exception:
        pass

получатели = list(s.execute(
    "SELECT id, inn, email, domain, company_name, segment FROM recipients"
    " WHERE segment='meyer'"))
print("\nбаза: получателей segment='meyer': %d" % len(получатели))

ш = Counter()
инн_ок, стр_ок = set(), []
for р in получатели:
    inn, em, dom = str(р["inn"] or ""), str(р["email"] or "").lower(), норм(р["domain"])
    ш["0. всего"] += 1
    п = паспорт.get(inn)
    if not п:
        continue
    ш["1. есть паспорт"] += 1
    сайт, блоков = п
    совпал = bool(сайт) and dom == сайт
    с_сайта = сайт in источник.get((inn, em), set()) if сайт else False
    if not (совпал or с_сайта):
        continue
    ш["2. почта с сайта паспорта / домен совпал"] += 1
    v = выручка.get(inn)
    if v is None:
        ш["   (выручка неизвестна)"] += 1
        continue
    if v < ПОРОГ:
        continue
    ш["3. выручка >= 30 млн"] += 1
    инн_ок.add(inn)
    стр_ок.append((inn, блоков, v))
    if inn not in писали:
        ш["4. и ещё НЕ писали"] += 1

print("\n=== ВОРОНКА (адреса) ===")
for k in sorted(ш):
    print("  %-42s %6d" % (k, ш[k]))

инн_не_писали = {i for i in инн_ок if i not in писали}
print("\n=== ИТОГ ===")
print("  адресов, прошедших все три критерия : %d" % ш["3. выручка >= 30 млн"])
print("  УНИКАЛЬНЫХ КОМПАНИЙ (ИНН)          : %d" % len(инн_ок))
print("  из них ещё не писали               : %d" % len(инн_не_писали))
if стр_ок:
    б = sorted(x[1] for x in стр_ок)
    в = sorted(x[2] for x in стр_ок)
    print("  блоков паспорта: медиана %d, 10-90%% %d-%d"
          % (б[len(б) // 2], б[len(б) // 10], б[-max(1, len(б) // 10)]))
    print("  выручка млн: медиана %.0f, 10-90%% %.0f-%.0f"
          % (в[len(в) // 2] / 1e6, в[len(в) // 10] / 1e6, в[-max(1, len(в) // 10)] / 1e6))
