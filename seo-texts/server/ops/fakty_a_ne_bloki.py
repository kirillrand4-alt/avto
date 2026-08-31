# -*- coding: utf-8 -*-
"""Считаем паспорт теми полями, которые код РЕАЛЬНО читает.

Из двадцати блоков в промпт уходит шесть: partiya_gen._ПОЛЯ_ПАСПОРТА =
("цитата","продукция","оборудование_линии","сырьё","масштаб","мощности"),
линза берёт пять из них плюс упаковка_фасовка. Остальные четырнадцать не
видит никто, и считать их — обманывать себя. Соседняя сессия права.
"""
import json
import re
import sqlite3
from collections import Counter

ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб",
        "мощности")
ЛИНЗА = ("продукция", "сырьё", "мощности", "упаковка_фасовка", "расширение")
С_САЙТА = ("own-site", "обзвон-сайт", "сайт:справочник")
ПОРОГ_ВЫР = 30_000_000


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def домен(з):
    з = str(з or "").strip().lower()
    з = re.sub(r"^[a-z]+://", "", з).split("/")[0].split("?")[0].strip(".")
    return з[4:] if з.startswith("www.") else (з if "." in з else "")


def мера(сырое, ключи):
    """(-> сколько НЕПУСТЫХ полей, сколько всего пунктов в них)."""
    try:
        d = json.loads(сырое or "{}") or {}
    except Exception:                                         # noqa: BLE001
        return 0, 0
    полей = пунктов = 0
    for к in ключи:
        v = d.get(к)
        if isinstance(v, str):
            v = [v] if v.strip() else []
        if isinstance(v, (list, tuple)) and len(v):
            полей += 1
            пунктов += len(v)
    return полей, пунктов


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row
поля6, пункты6, все20 = {}, {}, {}
for r in e.execute("SELECT inn, facts_json FROM site_facts"):
    и = цифры(r["inn"])
    п, шт = мера(r["facts_json"], ПОЛЯ)
    поля6[и], пункты6[и] = п, шт
    все20[и] = мера(r["facts_json"],
                    json.loads(r["facts_json"] or "{}").keys()
                    if r["facts_json"] else [])[0]
компании, почта_ок = {}, set()
for r in e.execute("SELECT inn, revenue_rub, site, cand_site FROM companies"
                   " WHERE division LIKE '%meyer%'"):
    и = цифры(r["inn"])
    if и:
        компании[и] = (r["revenue_rub"],
                       домен(r["site"]) or домен(r["cand_site"]))
for r in e.execute("SELECT inn, email, source, probe_verdict FROM emails"):
    и = цифры(r["inn"])
    if и not in компании:
        continue
    а = str(r["email"] or "").strip().lower()
    if "@" not in а or (r["probe_verdict"] or "").strip() in ("нет ящика", "нет MX"):
        continue
    if (r["source"] or "").strip() in С_САЙТА or (
            компании[и][1] and а.split("@")[-1] == компании[и][1]):
        почта_ок.add(и)
e.close()

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
написано = set()
for зпр in ("SELECT DISTINCT inn FROM confirm_reviews WHERE inn IS NOT NULL",
            "SELECT DISTINCT r.inn FROM messages m JOIN recipients r"
            "  ON r.id=m.recipient_id WHERE r.inn IS NOT NULL"):
    написано |= {цифры(r[0]) for r in s.execute(зпр)}
стоп = {цифры(r[0]) for r in s.execute(
    "SELECT value FROM suppression WHERE scope='inn'"
    "   AND (expires_at IS NULL OR expires_at='')")}
партия = {цифры(r[0]) for r in s.execute(
    "SELECT DISTINCT inn FROM confirm_reviews WHERE campaign_id=11"
    "   AND created_at >= '2026-08-31' AND inn IS NOT NULL")}
s.close()


def медиана(зн):
    зн = sorted(зн)
    return зн[len(зн) // 2] if зн else 0


print("=== СЕГОДНЯШНЯЯ ПАРТИЯ (%d компаний) ===" % len(партия))
пп = [поля6.get(и, 0) for и in партия]
пу = [пункты6.get(и, 0) for и in партия]
дв = [все20.get(и, 0) for и in партия]
print("   по 20 блокам (моя прежняя мера): медиана %d" % медиана(дв))
print("   по 6 полям, что читает код:      медиана %d, 10%%–90%% %d–%d, мин %d"
      % (медиана(пп), sorted(пп)[len(пп) // 10], sorted(пп)[len(пп) * 9 // 10],
         min(пп) if пп else 0))
print("   пунктов внутри них:              медиана %d" % медиана(пу))

свободны = []
без_выручки = 0
for и, (выр, _) in компании.items():
    if и in написано or и in стоп or и not in почта_ок:
        continue
    известна = not (выр is None or int(выр or 0) == 0)
    if известна and int(выр) < ПОРОГ_ВЫР:
        continue
    if not известна:
        без_выручки += 1
    свободны.append(и)

print("\n=== СВОБОДНЫЙ ПУЛ ПОД ФИЛЬТР ВЛАДЕЛЬЦА ===")
print("   всего: %d, из них выручка НЕИЗВЕСТНА: %d (их соседняя сессия"
      " выбрасывает)" % (len(свободны), без_выручки))
только_богатые = [и for и in свободны
                  if компании[и][0] and int(компании[и][0]) >= ПОРОГ_ВЫР]
print("   только с выручкой от 30 млн: %d" % len(только_богатые))

print("\n=== СКОЛЬКО ОСТАЁТСЯ ПРИ ПОРОГЕ ПО 6 ПОЛЯМ ===")
print("   %-14s %10s %10s" % ("порог", "весь пул", "только с выручкой"))
for порог in (1, 2, 3, 4, 5, 6):
    a = len([и for и in свободны if поля6.get(и, 0) >= порог])
    b = len([и for и in только_богатые if поля6.get(и, 0) >= порог])
    print("   от %d полей   %10d %10d" % (порог, a, b))

print("\n=== ИТОГ ===")
м = медиана(пп)
на_уровне = [и for и in свободны if поля6.get(и, 0) >= м]
print("медиана партии по читаемым полям: %d" % м)
print("на этом уровне свободных компаний: %d → примерно %d писем при 91%%"
      % (len(на_уровне), int(len(на_уровне) * 0.91)))
