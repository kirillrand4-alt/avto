# -*- coding: utf-8 -*-
"""Свой ли сайт: сверка имени с доменом плюс таблица разногласий."""
import io
import json
import re
import sqlite3
from collections import Counter

ТР = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
      "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
      "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
      "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
      "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}
ОПФ = ("общество с ограниченной ответственностью", "ооо", "ао", "пао", "зао",
       "оао", "спок", "по", "нпк", "тд", "пк", "спк", "кфх")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def домен(з):
    з = str(з or "").strip().lower()
    з = re.sub(r"^[a-z]+://", "", з).split("/")[0].split("?")[0].strip(".")
    з = з[4:] if з.startswith("www.") else з
    return з.split(".")[0] if "." in з else ""


def латиница(з):
    з = str(з or "").lower()
    for о in ОПФ:
        з = з.replace(о, " ")
    з = re.sub(r"[^а-яёa-z]+", "", з)
    return "".join(ТР.get(c, c) for c in з)


ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
попыток, готово, итогов = Counter(), set(), Counter()
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    for с in f.readlines():
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        и = цифры(z.get("inn"))
        if not и:
            continue
        э = str(z.get("этап") or "")
        if э == "отмена_попытки":
            попыток[и] = max(0, попыток[и] - 1)
            continue
        if z.get("ок") or z.get("тело"):
            готово.add(и)
        if э != "итог":
            попыток[и] += 1
        else:
            итогов[и] += 1
цель = [и for и in попыток
        if попыток[и] >= 3 and и not in готово and not итогов[и]]

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row
карт, разно = {}, {}
for i in range(0, len(цель), 400):
    ч = цель[i:i + 400]
    for r in e.execute("SELECT inn, name, short_name, site, site_source, okved"
                       "  FROM companies WHERE inn IN (%s)"
                       % ",".join("?" * len(ч)), ч):
        карт[цифры(r["inn"])] = dict(r)
    for r in e.execute("SELECT inn, nash_site, obzvon_site, prichina"
                       "  FROM raznoglasie_sait WHERE inn IN (%s)"
                       % ",".join("?" * len(ч)), ч):
        разно[цифры(r["inn"])] = dict(r)
пасп = {}
for i in range(0, len(цель), 400):
    ч = цель[i:i + 400]
    for r in e.execute("SELECT inn, facts_json FROM site_facts WHERE inn IN (%s)"
                       % ",".join("?" * len(ч)), ч):
        try:
            d = json.loads(r["facts_json"] or "{}") or {}
        except Exception:                                     # noqa: BLE001
            d = {}
        п = d.get("продукция") or []
        if isinstance(п, str):
            п = [п]
        пасп[цифры(r["inn"])] = "; ".join(str(x) for x in п[:2])
e.close()

свод = Counter()
сомнительные = []
for и in цель:
    к = карт.get(и)
    if not к:
        свод["нет карточки"] += 1
        continue
    д = домен(к.get("site"))
    if not д:
        свод["сайта нет вовсе"] += 1
        continue
    имя = латиница(к.get("short_name") or к.get("name"))
    ист = str(к.get("site_source") or "")
    if имя and (имя[:6] in д or д[:6] in имя):
        свод["имя совпало с доменом — свой"] += 1
    elif "инн-на-сайте" in ист:
        свод["ИНН найден на сайте — свой"] += 1
    elif "имя-на-сайте" in ист:
        свод["имя найдено на сайте — вероятно свой"] += 1
    else:
        свод["связь не подтверждена"] += 1
        if len(сомнительные) < 14:
            сомнительные.append((к.get("name"), к.get("okved"), к.get("site"),
                                 ист or "источник не записан", пасп.get(и, "")))

print("=== СВОЙ ЛИ САЙТ У %d ОТСЕЯННЫХ ===" % len(цель))
for к, n in свод.most_common():
    print("   %-38s %5d" % (к, n))
print("\n   в таблице разногласий числятся: %d" % len(разно))
if разно:
    for п, n in Counter(str(v.get("prichina"))[:40]
                        for v in разно.values()).most_common(5):
        print("      %4d  %s" % (n, п))

print("\n=== ГДЕ СВЯЗЬ НЕ ПОДТВЕРЖДЕНА (глазами) ===")
for имя, окв, сайт, ист, прод in сомнительные:
    print("   %-30s %-10s %-26s [%s]"
          % (str(имя)[:30], str(окв)[:10], str(сайт)[:26], ист[:22]))
    if прод:
        print("        сайт продаёт: %s" % прод[:90])
