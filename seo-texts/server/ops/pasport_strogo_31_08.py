# -*- coding: utf-8 -*-
"""Только чтение: заполненность полей паспорта и счёт при СТРОГОМ определении.

Мягкое определение (любое непустое поле) считает паспортом и служебные поля
«источники», «уверенность», и даже «ошибка». Строгое считает только факты
о производстве."""
import json
import sqlite3
from collections import Counter

# поля-факты о предприятии
СУТЬ = ("продукция", "упаковка_фасовка", "сырьё", "мощности", "контроль_качества",
        "экспорт", "оборудование_линии", "клиенты", "год_основания",
        "география_поставок", "масштаб", "расширение", "газы", "энергохозяйство",
        "новости")
# служебные и диагностические — фактами не являются
СЛУЖЕБНЫЕ = ("источники", "уверенность", "цитата", "разбор_КЦ", "разбор_мейер",
             "свежая_новость", "примечание", "ошибка", "комментарий", "замечание",
             "причина", "причина_отсутствия_данных", "причина_отказа")
ПОРОГ_В = 30_000_000


def норм(d):
    d = str(d or "").strip().lower()
    for п in ("https://", "http://"):
        if d.startswith(п):
            d = d[len(п):]
    d = d.split("/")[0].split("?")[0].split(":")[0]
    return (d[4:] if d.startswith("www.") else d).strip(". ")


def непусто(v):
    return v not in (None, "", [], {}, "нет")


e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

пасп = {}
поле_есть, поле_полно = Counter(), Counter()
for р in e.execute("SELECT inn, facts_json, site FROM site_facts"):
    try:
        f = json.loads(р["facts_json"] or "{}")
    except Exception:
        continue
    мягко = sum(1 for v in f.values() if непусто(v))
    строго = sum(1 for k, v in f.items() if k in СУТЬ and непусто(v))
    пасп[str(р["inn"])] = (норм(р["site"]), мягко, строго)
    for k, v in f.items():
        поле_есть[k] += 1
        if непусто(v):
            поле_полно[k] += 1

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

строки = list(s.execute("SELECT inn, email, domain FROM recipients WHERE segment='meyer'"))
print("=== ЗАПОЛНЕННОСТЬ ПОЛЕЙ (по всем карточкам site_facts) ===")
print("  %-24s %9s %9s" % ("поле", "карточек", "непусто"))
for k, n in поле_есть.most_common(30):
    род = "факт" if k in СУТЬ else ("служебное" if k in СЛУЖЕБНЫЕ else "?")
    print("  %-24s %9d %8d (%3.0f%%)  %s"
          % (k, n, поле_полно[k], 100.0 * поле_полно[k] / max(1, n), род))


def счёт(мин_строго):
    инн, св = set(), set()
    for р in строки:
        i, em, dom = str(р["inn"] or ""), str(р["email"] or "").lower(), норм(р["domain"])
        p = пасп.get(i)
        if not p:
            continue
        сайт, мягко, строго = p
        if строго < мин_строго:
            continue
        if not (сайт and (dom == сайт or сайт in ист.get((i, em), set()))):
            continue
        v = выр.get(i)
        if v is None or v < ПОРОГ_В:
            continue
        инн.add(i)
        if i not in писали:
            св.add(i)
    return len(инн), len(св)


print("\n=== ИТОГ: как порог «паспорта» двигает число ===")
print("  критерии 2 и 3 те же; меняется только требование к паспорту")
print("  %-42s %9s %12s" % ("определение паспорта", "компаний", "не писали"))
a, b = счёт(0)
print("  %-42s %9d %12d" % ("мягкое: любое непустое поле (как я считал)", a, b))
for n in (1, 2, 3, 4, 5, 6, 8):
    a, b = счёт(n)
    print("  %-42s %9d %12d" % ("строгое: полей-ФАКТОВ >= %d" % n, a, b))
