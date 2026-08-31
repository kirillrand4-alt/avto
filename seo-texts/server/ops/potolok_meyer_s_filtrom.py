# -*- coding: utf-8 -*-
"""Уточнение: сколько из недозаведённых проходят ЕЩЁ И твой фильтр.

Фильтр владельца: выручка неизвестна или от 30 млн; почта взята с сайта либо
стоит на домене их сайта.
"""
import re
import sqlite3
from collections import Counter

ПОРОГ = 30_000_000
С_САЙТА = ("own-site", "обзвон-сайт", "сайт:справочник")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def домен(з):
    з = str(з or "").strip().lower()
    з = re.sub(r"^[a-z]+://", "", з).split("/")[0].split("?")[0].strip(".")
    if з.startswith("www."):
        з = з[4:]
    return з if "." in з else ""


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row
паспорта = {цифры(r[0]) for r in e.execute("SELECT inn FROM site_facts")}
компании = {}
for r in e.execute("SELECT inn, revenue_rub, site, cand_site FROM companies"
                   " WHERE division LIKE '%meyer%'"):
    и = цифры(r["inn"])
    if и:
        компании[и] = (r["revenue_rub"],
                       домен(r["site"]) or домен(r["cand_site"]))
годная_почта = {}
for r in e.execute("SELECT inn, email, source, probe_verdict FROM emails"):
    и = цифры(r["inn"])
    if и not in компании:
        continue
    адр = str(r["email"] or "").strip().lower()
    if "@" not in адр or (r["probe_verdict"] or "").strip() in ("нет ящика", "нет MX"):
        continue
    ист = (r["source"] or "").strip()
    if ист in С_САЙТА or (компании[и][1] and адр.split("@")[-1] == компании[и][1]):
        годная_почта.setdefault(и, []).append(адр)
e.close()

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
написано = set()
for зпр in ("SELECT DISTINCT inn FROM confirm_reviews WHERE inn IS NOT NULL",
            "SELECT DISTINCT r.inn FROM messages m JOIN recipients r"
            "  ON r.id=m.recipient_id WHERE r.inn IS NOT NULL"):
    написано |= {цифры(r[0]) for r in s.execute(зпр)}
заведены = {цифры(r[0]) for r in s.execute(
    "SELECT DISTINCT inn FROM recipients WHERE inn IS NOT NULL")}
стоп = {цифры(r[0]) for r in s.execute(
    "SELECT value FROM suppression WHERE scope='inn'"
    "   AND (expires_at IS NULL OR expires_at='')")}
s.close()

сч = Counter()
for и, (выручка, _д) in компании.items():
    if и in написано or и in стоп:
        continue
    выр_ок = (выручка is None or int(выручка or 0) == 0
              or int(выручка) >= ПОРОГ)
    есть_почта = и in годная_почта
    есть_пасп = и in паспорта
    уже_заведён = и in заведены
    if not (выр_ок and есть_почта):
        сч["не проходит фильтр владельца"] += 1
        continue
    ключ = ("уже заведён" if уже_заведён else "надо заводить") + \
           (", с паспортом" if есть_пасп else ", без паспорта")
    сч[ключ] += 1

print("=== НЕНАПИСАННЫЕ МЕЙЕРОВСКИЕ ПОД ТВОЙ ФИЛЬТР ===")
for к, n in сч.most_common():
    print("   %-34s %6d" % (к, n))

зав_п = сч["уже заведён, с паспортом"]
нов_п = сч["надо заводить, с паспортом"]
зав_б = сч["уже заведён, без паспорта"]
нов_б = сч["надо заводить, без паспорта"]
print("\n=== ИТОГ ===")
print("проходят фильтр И имеют паспорт: %d  →  %d годных писем при 91%%"
      % (зав_п + нов_п, int((зав_п + нов_п) * 0.91)))
print("   из них заведены получателями: %d (можно писать хоть сейчас)" % зав_п)
print("   надо завести в панель:        %d" % нов_п)
print("проходят фильтр, но без паспорта: %d — сперва обойти сайты" % (зав_б + нов_б))
