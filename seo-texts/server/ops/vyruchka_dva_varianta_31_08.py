# -*- coding: utf-8 -*-
"""Только чтение: критерий выручки в двух прочтениях.

A) строго  : выручка >= 30 млн (как я считал)
B) широко  : выручка >= 30 млн ЛИБО неизвестна (как уточнил владелец)
Плюс: сколько в пуле вообще неизвестной выручки."""
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
for р in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL"):
    try:
        выр[str(р["inn"])] = float(р["revenue_rub"])
    except Exception:
        pass
ист = {}
for таб, кол in (("emails", "source_url"), ("email_sources", "url")):
    for р in e.execute("SELECT inn, email, %s u FROM %s" % (кол, таб)):
        d = норм(р["u"])
        if d:
            ист.setdefault((str(р["inn"]), str(р["email"] or "").lower()), set()).add(d)
писали = {str(р["inn"]) for р in s.execute(
    "SELECT DISTINCT inn FROM confirm_reviews WHERE inn IS NOT NULL")}
rid2 = {р["id"]: str(р["inn"] or "") for р in s.execute("SELECT id, inn FROM recipients")}
for р in s.execute("SELECT DISTINCT recipient_id FROM ai_letter_log WHERE recipient_id IS NOT NULL"):
    if rid2.get(р["recipient_id"]):
        писали.add(rid2[р["recipient_id"]])

# компании, прошедшие критерии 1-2 (паспорт непустой + почта)
прошли = {}
for р in s.execute("SELECT inn, email, domain FROM recipients WHERE segment='meyer'"):
    i, em, dom = str(р["inn"] or ""), str(р["email"] or "").lower(), норм(р["domain"])
    p = пасп.get(i)
    if not p:
        continue
    сайт, фактов = p
    if not (сайт and (dom == сайт or сайт in ист.get((i, em), set()))):
        continue
    прошли[i] = фактов

кл = Counter()
for i in прошли:
    v = выр.get(i)
    кл["выручка >= 30 млн" if (v is not None and v >= ПОРОГ)
       else ("выручка НЕИЗВЕСТНА" if v is None else "выручка < 30 млн")] += 1
print("=== компании, прошедшие критерии 1-2 (паспорт + почта): %d ===" % len(прошли))
for k, v in кл.most_common():
    print("  %-24s %6d (%4.1f%%)" % (k, v, 100.0 * v / len(прошли)))

print("\n=== ВСЕ мейеровские компании (без критерия почты) ===")
все_м = {str(р["inn"]) for р in s.execute(
    "SELECT DISTINCT inn FROM recipients WHERE segment='meyer' AND inn IS NOT NULL")}
к2 = Counter()
for i in все_м:
    v = выр.get(i)
    к2["выручка >= 30 млн" if (v is not None and v >= ПОРОГ)
       else ("выручка НЕИЗВЕСТНА" if v is None else "выручка < 30 млн")] += 1
print("  всего компаний: %d" % len(все_м))
for k, v in к2.most_common():
    print("  %-24s %6d (%4.1f%%)" % (k, v, 100.0 * v / len(все_м)))


def счёт(мин, широко):
    вс, св = 0, 0
    for i, ф in прошли.items():
        if ф < мин:
            continue
        v = выр.get(i)
        ок = (v is None) if широко and v is None else (v is not None and v >= ПОРОГ)
        if not ок:
            continue
        вс += 1
        if i not in писали:
            св += 1
    return вс, св


print("\n=== ИТОГ: порог паспорта x прочтение выручки ===")
print("  %-26s %11s %11s %11s %11s" % ("порог (полей-фактов)",
                                       "A: >=30млн", "не писали", "B: +неизв.", "не писали"))
for м in (1, 2, 3, 4, 5, 6, 8):
    a1, a2 = счёт(м, False)
    b1, b2 = счёт(м, True)
    print("  %-26s %11d %11d %11d %11d" % (">= %d" % м, a1, a2, b1, b2))
