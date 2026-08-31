# -*- coding: utf-8 -*-
"""Сколько мейеровских компаний ещё не написано при условиях владельца.

Условия: направление meyer; письма ещё не было; выручка неизвестна ИЛИ от
30 млн; почта либо взята С САЙТА компании, либо стоит НА ТОМ ЖЕ ДОМЕНЕ, что и
её сайт.

Считаем воронкой: сначала голое условие владельца, потом что от него остаётся
после живых заслонов (стоп-лист, мёртвые пробы, конкуренты, ликвидированные).
"""
import re
import sqlite3
from collections import Counter

ПОРОГ = 30_000_000
С_САЙТА = ("own-site", "обзвон-сайт", "сайт:справочник")
ПРИГОВОР = ("нет ящика", "нет MX")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def домен_сайта(з):
    з = str(з or "").strip().lower()
    if not з:
        return ""
    з = re.sub(r"^[a-z]+://", "", з).split("/")[0].split("?")[0]
    з = з.split("@")[-1].strip().strip(".")
    if з.startswith("www."):
        з = з[4:]
    return з if "." in з else ""


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
e.row_factory = sqlite3.Row

# --- 1. мейеровские компании с нужной выручкой -------------------------------
компании = {}
for r in e.execute(
        "SELECT inn, name, division, revenue_rub, site, cand_site, "
        "       is_competitor, status_egrul "
        "  FROM companies WHERE division LIKE '%meyer%'"):
    и = цифры(r["inn"])
    if not и:
        continue
    компании[и] = {
        "name": r["name"], "div": (r["division"] or "").strip(),
        "rev": r["revenue_rub"],
        "site": домен_сайта(r["site"]) or домен_сайта(r["cand_site"]),
        "konk": int(r["is_competitor"] or 0),
        "status": (r["status_egrul"] or "").strip(),
    }
print("мейеровских компаний в обогащении: %d" % len(компании))

годная_выручка = {и for и, c in компании.items()
                  if (c["rev"] is None or int(c["rev"] or 0) == 0
                      or int(c["rev"]) >= ПОРОГ)}
print("из них выручка неизвестна или от 30 млн: %d" % len(годная_выручка))

# --- 2. их адреса с нужным происхождением ------------------------------------
адреса = {}
плохие_пробы = set()
for r in e.execute("SELECT inn, email, source, probe_verdict FROM emails"):
    и = цифры(r["inn"])
    if и not in годная_выручка:
        continue
    адр = str(r["email"] or "").strip().lower()
    if "@" not in адр:
        continue
    ист = (r["source"] or "").strip()
    дом = адр.split("@")[-1]
    с_сайта = ист in С_САЙТА
    свой_домен = bool(компании[и]["site"]) and дом == компании[и]["site"]
    if not (с_сайта or свой_домен):
        continue
    if (r["probe_verdict"] or "").strip() in ПРИГОВОР:
        плохие_пробы.add(адр)
        continue
    адреса.setdefault(и, []).append((адр, с_сайта, свой_домен))
e.close()
print("компаний с подходящей почтой: %d (адресов %d); "
      "адресов отсеяно приговором пробы: %d"
      % (len(адреса), sum(len(v) for v in адреса.values()), len(плохие_пробы)))

# --- 3. кому уже писали и кто в стоп-листе -----------------------------------
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
s.row_factory = sqlite3.Row
отправлено = {цифры(r[0]) for r in s.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.sent_at IS NOT NULL AND r.inn IS NOT NULL")}
всякое_письмо = set(отправлено)
for зпр in ("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id"
            "  WHERE r.inn IS NOT NULL",
            "SELECT DISTINCT inn FROM confirm_reviews WHERE inn IS NOT NULL",
            "SELECT DISTINCT r.inn FROM ai_letter_log a JOIN recipients r"
            "  ON r.id=a.recipient_id WHERE r.inn IS NOT NULL"):
    всякое_письмо |= {цифры(r[0]) for r in s.execute(зпр)}
всякое_письмо.discard("")

стоп_инн, стоп_адр, стоп_дом = set(), set(), set()
for r in s.execute("SELECT scope, value, expires_at FROM suppression"):
    if r["expires_at"]:
        continue
    з = str(r["value"] or "").strip().lower()
    if r["scope"] == "inn":
        стоп_инн.add(цифры(з))
    elif r["scope"] == "email":
        стоп_адр.add(з)
    elif r["scope"] == "domain":
        стоп_дом.add(з)
мёртвые_probe = {str(r[0] or "").strip().lower() for r in s.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
загружены = {цифры(r[0]) for r in s.execute(
    "SELECT DISTINCT inn FROM recipients WHERE inn IS NOT NULL")}
s.close()

# --- 4. воронка ---------------------------------------------------------------
основа = set(адреса)
не_писали_совсем = основа - всякое_письмо
не_отправляли = основа - отправлено

годные = {}
причины = Counter()
for и in не_писали_совсем:
    c = компании[и]
    if и in стоп_инн:
        причины["ИНН в стоп-листе"] += 1
        continue
    if c["konk"]:
        причины["конкурент"] += 1
        continue
    if any(х in c["status"].lower() for х in ("ликвид", "банкрот", "прекращ")):
        причины["ликвидирована/банкрот"] += 1
        continue
    живые = [а for а, сс, сд in адреса[и]
             if а not in стоп_адр and а.split("@")[-1] not in стоп_дом
             and а not in мёртвые_probe]
    if not живые:
        причины["все адреса в стоп-листе или мертвы"] += 1
        continue
    годные[и] = живые

с_сайта_только = sum(1 for и in годные
                     if any(сс for _, сс, сд in адреса[и] if not сд))
свой_домен_есть = sum(1 for и in годные
                      if any(сд for _, сс, сд in адреса[и]))
без_выручки = sum(1 for и in годные if not компании[и]["rev"])
с_выручкой = len(годные) - без_выручки
загруженных = len(set(годные) & загружены)

print("\n=== ВОРОНКА ===")
print("мейеровских компаний                                  %7d" % len(компании))
print("  выручка неизвестна или от 30 млн                    %7d" % len(годная_выручка))
print("    почта с сайта либо на своём домене                %7d" % len(основа))
print("      никогда не писали (нет даже черновика)          %7d" % len(не_писали_совсем))
print("      (для справки: не ОТПРАВЛЯЛИ, черновик мог быть) %7d" % len(не_отправляли))
print("        минус стоп-лист, конкуренты, ликвидированные, мёртвые адреса:")
for п, n in причины.most_common():
    print("            %-42s -%6d" % (п, n))

print("\n=== ОТВЕТ ===")
print("осталось написать: %d компаний, живых адресов у них %d"
      % (len(годные), sum(len(v) for v in годные.values())))
print("   из них выручка неизвестна: %d; от 30 млн: %d" % (без_выручки, с_выручкой))
print("   почта на СВОЁМ домене:     %d" % свой_домен_есть)
print("   почта с сайта на чужом домене (mail.ru и подобные): %d" % с_сайта_только)
print("   уже заведены получателями в панели: %d; надо заводить: %d"
      % (загруженных, len(годные) - загруженных))
