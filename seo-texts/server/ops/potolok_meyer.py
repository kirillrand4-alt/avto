# -*- coding: utf-8 -*-
"""Сколько ещё годных писем Meyer можно выжать. Воронка по трём слоям.

Замер сегодняшнего прогона: у компаний С ПАСПОРТОМ сайта отдача 91%.
Паспорт — главный предиктор, поэтому считаем отдельно тех, у кого он есть.
"""
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.ai_letter import target_division                  # noqa: E402

ОТДАЧА_С_ПАСПОРТОМ = 0.91
СВОЙ_СЕРВЕР = ("other", "unknown", "")
ГРУППА = "Партия 935"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
паспорта = {цифры(r[0]) for r in e.execute("SELECT inn FROM site_facts")}
print("паспортов сайта в обогащении: %d" % len(паспорта))
мейер_компании = {}
for r in e.execute("SELECT inn, division, best_email, site FROM companies"
                   " WHERE division LIKE '%meyer%'"):
    и = цифры(r[0])
    if и:
        мейер_компании[и] = (r[1], r[2], r[3])
почта_у = set()
for r in e.execute("SELECT DISTINCT inn FROM emails WHERE email LIKE '%@%'"):
    почта_у.add(цифры(r[0]))
e.close()
print("мейеровских компаний в обогащении: %d; из них с паспортом: %d"
      % (len(мейер_компании), len(set(мейер_компании) & паспорта)))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
s.row_factory = sqlite3.Row

написано = set()
for зпр in ("SELECT DISTINCT inn FROM confirm_reviews WHERE inn IS NOT NULL",
            "SELECT DISTINCT r.inn FROM messages m JOIN recipients r"
            "  ON r.id=m.recipient_id WHERE r.inn IS NOT NULL"):
    написано |= {цифры(r[0]) for r in s.execute(зпр)}
написано.discard("")
print("фирм, которым письмо уже писали: %d" % len(написано))

стоп_инн, стоп_адр, стоп_дом = set(), set(), set()
for r in s.execute("SELECT scope, value, expires_at FROM suppression"
                   " WHERE expires_at IS NULL OR expires_at=''"):
    з = str(r["value"] or "").strip().lower()
    if r["scope"] == "inn":
        стоп_инн.add(цифры(з))
    elif r["scope"] == "email":
        стоп_адр.add(з)
    elif r["scope"] == "domain":
        стоп_дом.add(з)
мёртвые = {str(r[0] or "").strip().lower() for r in s.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}

# ---- слой 1: свободные в группе «Партия 935» --------------------------------
группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
слой1 = Counter()
видели = set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    инн = цифры(getattr(rec, "inn", ""))
    адр = str(getattr(rec, "email", "") or "").strip().lower()
    if not инн or not адр or инн in видели:
        continue
    видели.add(инн)
    if инн in написано or инн in стоп_инн or адр in мёртвые:
        continue
    if адр in стоп_адр or адр.split("@")[-1] in стоп_дом:
        continue
    доп = getattr(rec, "extra", None) or {}
    if str(доп.get("ne_nash_ni_odnomu") or "").strip():
        continue
    d, _ = target_division({"company_name": getattr(rec, "company_name", "") or "",
                            "okved": getattr(rec, "okved", "") or "",
                            "activity": str(доп.get("activity") or ""),
                            "extra": доп}, default="kc")
    if d != "meyer":
        continue
    свой = str(getattr(rec, "mx_provider", "") or "").strip().lower() in СВОЙ_СЕРВЕР
    ключ = ("с паспортом" if инн in паспорта else "без паспорта") + \
           (", свой сервер" if свой else ", публичная почта")
    слой1[ключ] += 1

# ---- слой 2: заведены получателями, но вне группы ---------------------------
слой2 = Counter()
for r in s.execute("SELECT DISTINCT inn, email, mx_provider FROM recipients"
                   " WHERE inn IS NOT NULL AND email LIKE '%@%'"):
    инн = цифры(r["inn"])
    адр = str(r["email"] or "").strip().lower()
    if not инн or инн in видели or инн in написано or инн in стоп_инн:
        continue
    if адр in мёртвые or адр in стоп_адр or адр.split("@")[-1] in стоп_дом:
        continue
    if инн not in мейер_компании:
        continue
    видели.add(инн)
    слой2["с паспортом" if инн in паспорта else "без паспорта"] += 1
s.close()

# ---- слой 3: есть в обогащении, но не заведены получателями -----------------
слой3 = Counter()
for инн in мейер_компании:
    if инн in видели or инн in написано or инн in стоп_инн:
        continue
    if инн not in почта_у:
        слой3["без почты вовсе"] += 1
        continue
    слой3["с паспортом" if инн in паспорта else "без паспорта"] += 1

print("\n=== СЛОЙ 1: СВОБОДНЫЕ В ГРУППЕ «Партия 935» ===")
for к, n in слой1.most_common():
    print("   %-32s %6d" % (к, n))
print("\n=== СЛОЙ 2: ЗАВЕДЕНЫ ПОЛУЧАТЕЛЯМИ, НО ВНЕ ГРУППЫ ===")
for к, n in слой2.most_common():
    print("   %-32s %6d" % (к, n))
print("\n=== СЛОЙ 3: ЕСТЬ В ОБОГАЩЕНИИ, ПОЛУЧАТЕЛЯМИ НЕ ЗАВЕДЕНЫ ===")
for к, n in слой3.most_common():
    print("   %-32s %6d" % (к, n))

п1 = слой1["с паспортом, публичная почта"]
п1к = слой1["с паспортом, свой сервер"]
п2 = слой2["с паспортом"]
п3 = слой3["с паспортом"]
без = (слой1["без паспорта, публичная почта"] + слой1["без паспорта, свой сервер"]
       + слой2["без паспорта"] + слой3["без паспорта"])

print("\n=== ИТОГ: СКОЛЬКО ГОДНЫХ ПИСЕМ ===")
print("с паспортом сайта — отдача замерена сегодня, 91%%:")
print("   в группе, публичная почта   %6d  →  %5d писем" % (п1, п1 * ОТДАЧА_С_ПАСПОРТОМ))
print("   в группе, свой сервер       %6d  →  %5d писем (в автоотправку не идут)"
      % (п1к, п1к * ОТДАЧА_С_ПАСПОРТОМ))
print("   вне группы, но заведены     %6d  →  %5d писем" % (п2, п2 * ОТДАЧА_С_ПАСПОРТОМ))
print("   только в обогащении         %6d  →  %5d писем (нужно завести)"
      % (п3, п3 * ОТДАЧА_С_ПАСПОРТОМ))
print("   ---")
print("   ВСЕГО с паспортом           %6d  →  %5d годных писем"
      % (п1 + п1к + п2 + п3, (п1 + п1к + п2 + п3) * ОТДАЧА_С_ПАСПОРТОМ))
print("\nбез паспорта сайта:           %6d — отдача неизвестна, исторически" % без)
print("   конвейер без паспортов давал 50-65%%; сперва обход сайтов")
print("\nбез почты вовсе:              %6d — сперва обогащение контактов"
      % слой3["без почты вовсе"])
