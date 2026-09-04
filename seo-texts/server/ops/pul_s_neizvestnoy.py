# -*- coding: utf-8 -*-
"""Пул по правилу владельца: выручка от 30 млн ЛИБО не известна, почта есть."""
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

# что вообще известно про каждую компанию свежего сбора
состояние = {}
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    и = str(z.get("inn") or "")
    if и not in свежие:
        continue
    if z.get("сбой"):
        состояние.setdefault(и, {"сбой": True})
        continue
    почты = [p.strip().lower() for p in
             re.split(r"[|,;]", str(z.get("emails_checko") or ""))
             if "@" in p]
    try:
        выр = int(str(z.get("revenue_rub") or "0") or 0)
    except ValueError:
        выр = 0
    состояние[и] = {"почты": почты, "выручка": выр, "сбой": False,
                    "оквэд": свежие[и][1], "имя": свежие[и][0],
                    "ссч": z.get("ssch")}

счёт = Counter()
годные = []
не_обошли = 0
for и, (имя, квэд) in свежие.items():
    с = состояние.get(и)
    if с is None:
        не_обошли += 1
        счёт["не обходили вовсе"] += 1
        continue
    if с.get("сбой"):
        счёт["обход не удался (выручка не известна)"] += 1
        continue
    if not с["почты"]:
        счёт["почты нет — писать некуда"] += 1
        continue
    в = с["выручка"]
    if в and в < ПОРОГ:
        счёт["выручка НИЖЕ 30 млн — отсев"] += 1
        continue
    счёт["ГОДНЫ: от 30 млн" if в else "ГОДНЫ: выручка не известна"] += 1
    годные.append((в, и, имя, квэд, с["почты"], с.get("ссч")))

от30 = счёт["ГОДНЫ: от 30 млн"]
неизв = счёт["ГОДНЫ: выручка не известна"]
адресов = sum(len(г[4]) for г in годные)
бесплатных = sum(1 for г in годные for п in г[4]
                 if п.split("@")[-1] in БЕСПЛАТНЫЕ)
коды = Counter(г[3][:7] for г in годные)

print("=" * 80)
print("=== СВОДКА: ПУЛ ПО ПРАВИЛУ «ОТ 30 МЛН ЛИБО НЕ ИЗВЕСТНА» ===")
print("компаний свежего сбора всего: %d" % len(свежие))
print("")
for к, в in счёт.most_common():
    print("   %-42s %6d" % (к, в))
print("")
print("=== ГОДНЫХ ВСЕГО: %d ===" % len(годные))
print("   от 30 млн:            %6d" % от30)
print("   выручка не известна:  %6d" % неизв)
print("   адресов у них:        %6d (бесплатных ящиков %d)"
      % (адресов, бесплатных))
print("")
print("--- по кодам ---")
for к, в in коды.most_common(8):
    print("   %-10s %6d" % (к, в))
print("")
print("--- примеры из тех, у кого выручка НЕ известна ---")
n = 0
for в, и, имя, квэд, почты, ссч in годные:
    if в:
        continue
    print("   %-13s %-34s %-9s ССЧ %-5s %s"
          % (и, имя[:34], квэд[:9], ссч or "—", почты[0][:30]))
    n += 1
    if n >= 6:
        break
