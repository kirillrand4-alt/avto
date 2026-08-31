# -*- coding: utf-8 -*-
"""Потолок Meyer заново: порог по НАПОЛНЕННОСТИ паспорта, а не по факту.

Сегодняшняя партия дала 91% отдачи, и у неё паспорт минимум 7 непустых
блоков, медиана 10. Значит осмысленный порог — 7, а не «паспорт есть»:
последним критерием проходят 99.7% сегмента, то есть он не фильтр.
"""
import json
import re
import sqlite3
from collections import Counter

ПОРОГ_ВЫР = 30_000_000
С_САЙТА = ("own-site", "обзвон-сайт", "сайт:справочник")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def домен(з):
    з = str(з or "").strip().lower()
    з = re.sub(r"^[a-z]+://", "", з).split("/")[0].split("?")[0].strip(".")
    return з[4:] if з.startswith("www.") else (з if "." in з else "")


def непустых(сырое):
    try:
        d = json.loads(сырое or "{}") or {}
    except Exception:                                         # noqa: BLE001
        return 0
    n = 0
    for v in (d.values() if isinstance(d, dict) else []):
        if isinstance(v, str):
            n += 1 if v.strip() else 0
        elif isinstance(v, (list, tuple, dict)):
            n += 1 if len(v) else 0
        elif v not in (None, 0, False):
            n += 1
    return n


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row
блоков = {}
for r in e.execute("SELECT inn, facts_json FROM site_facts"):
    блоков[цифры(r["inn"])] = непустых(r["facts_json"])
компании = {}
for r in e.execute("SELECT inn, revenue_rub, site, cand_site FROM companies"
                   " WHERE division LIKE '%meyer%'"):
    и = цифры(r["inn"])
    if и:
        компании[и] = (r["revenue_rub"],
                       домен(r["site"]) or домен(r["cand_site"]))
почта_ок = set()
for r in e.execute("SELECT inn, email, source, probe_verdict FROM emails"):
    и = цифры(r["inn"])
    if и not in компании:
        continue
    адр = str(r["email"] or "").strip().lower()
    if "@" not in адр or (r["probe_verdict"] or "").strip() in ("нет ящика", "нет MX"):
        continue
    ист = (r["source"] or "").strip()
    if ист in С_САЙТА or (компании[и][1] and адр.split("@")[-1] == компании[и][1]):
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
заведены = {цифры(r[0]) for r in s.execute(
    "SELECT DISTINCT inn FROM recipients WHERE inn IS NOT NULL")}
s.close()

свободны = []
for и, (выр, _д) in компании.items():
    if и in написано or и in стоп or и not in почта_ок:
        continue
    if not (выр is None or int(выр or 0) == 0 or int(выр) >= ПОРОГ_ВЫР):
        continue
    свободны.append((и, блоков.get(и, -1)))

print("=== НЕНАПИСАННЫЕ МЕЙЕРОВСКИЕ ПОД ФИЛЬТР ВЛАДЕЛЬЦА ===")
print("   всего: %d" % len(свободны))
расп = Counter(б for _, б in свободны)
print("   без паспорта вовсе: %d" % расп.get(-1, 0))
print("   паспорт пустой (0 блоков): %d" % расп.get(0, 0))

print("\n=== СКОЛЬКО ОСТАЁТСЯ ПРИ РАЗНЫХ ПОРОГАХ ===")
print("   %-24s %8s %10s %s" % ("порог", "компаний", "писем 91%", "заведены"))
for порог in (0, 1, 3, 5, 7, 8, 10, 12):
    годные = [и for и, б in свободны if б >= порог]
    зав = len([и for и in годные if и in заведены])
    print("   от %2d непустых блоков   %8d %10d %8d"
          % (порог, len(годные), int(len(годные) * 0.91), зав))

print("\n=== ИТОГ ===")
семь = [и for и, б in свободны if б >= 7]
print("порог 7 блоков — уровень сегодняшней партии (её минимум 7, медиана 10):")
print("   компаний %d → примерно %d годных писем при отдаче 91%%"
      % (len(семь), int(len(семь) * 0.91)))
print("   из них уже заведены получателями: %d"
      % len([и for и in семь if и in заведены]))
