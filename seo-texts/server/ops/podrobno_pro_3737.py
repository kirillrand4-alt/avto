# -*- coding: utf-8 -*-
"""Подробно про компании, готовые к письмам: откуда почта, выручка, профиль.

Источник — журнал ходилки Чеко: там и выручка, и почты, и ОКВЭД.
"""
import io
import json
import re
import sqlite3
from collections import Counter

ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"
ПОРОГ = 30_000_000
БЕСПЛАТНЫЕ = ("mail.ru", "yandex.ru", "ya.ru", "gmail.com", "bk.ru",
              "inbox.ru", "list.ru", "rambler.ru", "internet.ru")

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=180)
свежие = {}
for и, н, к in c.execute(
        "SELECT inn, name_short, okved_main FROM requisites "
        " WHERE src='checko-sbor-agro'"):
    свежие[str(и)] = (str(н or ""), str(к or ""))
c.close()

годные = []
видели = set()
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if z.get("сбой"):
        continue
    и = str(z.get("inn") or "")
    if и not in свежие or и in видели:
        continue
    почты = [p.strip().lower() for p in
             re.split(r"[|,;]", str(z.get("emails_checko") or ""))
             if "@" in p]
    if not почты:
        continue
    try:
        выр = int(str(z.get("revenue_rub") or "0") or 0)
    except ValueError:
        выр = 0
    if выр < ПОРОГ:
        continue
    видели.add(и)
    имя, квэд = свежие[и]
    годные.append({"инн": и, "имя": имя, "оквэд": квэд, "выручка": выр,
                   "почты": почты, "год": z.get("fin_god"),
                   "ссч": z.get("ssch")})

полосы = Counter()
классы = Counter()
коды = Counter()
типы_почт = Counter()
годы = Counter()
ссч_полосы = Counter()
for г in годные:
    в = г["выручка"]
    полосы["1 млрд и выше" if в >= 1_000_000_000 else
           "300 млн - 1 млрд" if в >= 300_000_000 else
           "100-300 млн" if в >= 100_000_000 else
           "30-100 млн"] += 1
    классы[г["оквэд"].split(".")[0] or "?"] += 1
    коды[г["оквэд"][:7] or "?"] += 1
    годы[str(г["год"] or "?")] += 1
    try:
        с_ссч = int(str(г["ссч"] or "0") or 0)
    except ValueError:
        с_ссч = 0
    ссч_полосы["250+" if с_ссч >= 250 else "100-249" if с_ссч >= 100 else
               "50-99" if с_ссч >= 50 else "1-49" if с_ссч >= 1 else
               "не известно"] += 1
    for п in г["почты"]:
        дом = п.split("@")[-1]
        типы_почт["бесплатный ящик" if дом in БЕСПЛАТНЫЕ
                  else "свой домен"] += 1

НАЗВ = {"01": "сельское хозяйство", "10": "производство продуктов",
        "11": "напитки", "46": "оптовая торговля", "03": "рыболовство",
        "52": "склады"}

print("=" * 82)
print("=== СВОДКА: КОМПАНИИ, ГОТОВЫЕ К ПИСЬМАМ ===")
print("всего: %d компаний, адресов у них %d"
      % (len(годные), sum(len(г["почты"]) for г in годные)))
print("")
print("ОТКУДА ПОЧТА: карточка контактов checko.ru, поле emails_checko.")
print("Собрана нашей ходилкой по ОГРН, источник у всех один и тот же.")
print("")
print("--- ВЫРУЧКА ---")
for к in ("1 млрд и выше", "300 млн - 1 млрд", "100-300 млн", "30-100 млн"):
    if полосы.get(к):
        print("   %-18s %6d" % (к, полосы[к]))
print("")
print("--- НАПРАВЛЕНИЕ (класс ОКВЭД) ---")
for к, в in классы.most_common(8):
    print("   %-4s %-28s %6d" % (к, НАЗВ.get(к, ""), в))
print("")
print("--- КОДЫ ПОДРОБНЕЕ ---")
for к, в in коды.most_common(10):
    print("   %-10s %6d" % (к, в))
print("")
print("--- ТИП ПОЧТЫ ---")
for к, в in типы_почт.most_common():
    print("   %-18s %6d" % (к, в))
print("")
print("--- ЧИСЛЕННОСТЬ (ССЧ) ---")
for к in ("250+", "100-249", "50-99", "1-49", "не известно"):
    if ссч_полосы.get(к):
        print("   %-14s %6d" % (к, ссч_полосы[к]))
print("")
print("--- ГОД ОТЧЁТНОСТИ ---")
for к, в in годы.most_common(5):
    print("   %-8s %6d" % (к, в))
print("")
print("--- ДЕСЯТЬ КРУПНЕЙШИХ ---")
for г in sorted(годные, key=lambda x: -x["выручка"])[:10]:
    print("   %-13s %-34s %-9s %14s  %s"
          % (г["инн"], г["имя"][:34], г["оквэд"][:9],
             format(г["выручка"], ",d"), г["почты"][0][:30]))
