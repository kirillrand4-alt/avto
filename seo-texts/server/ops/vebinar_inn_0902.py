# -*- coding: utf-8 -*-
"""Только чтение баз. Ищем ИНН для 230 участников вебинара:
по домену корпоративной почты и по нормализованному названию.
Полный результат кладём в vebinar_inn_rezultat.json, в консоль - сводку."""
import io
import json
import os
import re
import sqlite3
import sys

БАЗА = os.path.dirname(os.path.abspath(__file__))
уч = json.loads(io.open(os.path.join(БАЗА, "vebinar_uchastniki.json"),
                        encoding="utf-8").read())

ПУБЛИЧНЫЕ = {
    "mail.ru", "gmail.com", "yandex.ru", "list.ru", "bk.ru", "inbox.ru",
    "ya.ru", "rambler.ru", "mail.com", "icloud.com", "yandex.com",
    "internet.ru", "narod.ru", "outlook.com", "hotmail.com", "me.com",
    "yahoo.com", "vk.com", "protonmail.com", "bk.com",
}

ОПФ = re.compile(
    r"^(ооо|оао|зао|пао|ао|ип|нао|тд|торговый дом|гк|группа компаний|"
    r"фгуп|гуп|муп|мку|гбуз|нко|ано|кфх|спк|сельскохозяйственный "
    r"производственный кооператив|производственный кооператив)\b")


def норм(с):
    с = (с or "").lower().replace("ё", "е")
    с = re.sub(r"[\"'«»„“”`]", " ", с)
    с = re.sub(r"[^0-9a-zа-я ]+", " ", с)
    с = re.sub(r"\s+", " ", с).strip()
    было = None
    while было != с:
        было = с
        с = ОПФ.sub("", с).strip()
    return re.sub(r"\s+", "", с)


def домен_сайта(с):
    с = (с or "").strip().lower()
    if not с:
        return ""
    с = re.sub(r"^https?://", "", с)
    с = с.split("/")[0].split("?")[0]
    if с.startswith("www."):
        с = с[4:]
    return с


e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row

# --- индексы из companies ---
по_имени = {}
по_домену = {}
n_ком = 0
for р in e.execute("SELECT inn, name, short_name, site, cand_site, site_checko,"
                   " region, revenue_rub, division, best_email FROM companies"):
    n_ком += 1
    зап = {"inn": р["inn"], "name": р["name"], "region": р["region"],
           "revenue_rub": р["revenue_rub"], "division": р["division"]}
    for поле in ("name", "short_name"):
        н = норм(р[поле])
        if len(н) >= 3:
            по_имени.setdefault(н, []).append(зап)
    for поле in ("site", "cand_site", "site_checko"):
        д = домен_сайта(р[поле])
        if д and "." in д:
            по_домену.setdefault(д, []).append(зап)

print("companies: %d строк, имён %d, доменов %d" % (n_ком, len(по_имени), len(по_домену)))

# --- base_ref: есть ли там имя+инн ---
доп_имя = {}
try:
    бк = [r["name"] for r in e.execute("PRAGMA table_info(base_ref)")]
    print("base_ref колонки: %s" % ", ".join(бк))
    поле_имя = next((k for k in ("name", "short_name", "company_name",
                                 "naimenovanie") if k in бк), None)
    if "inn" in бк and поле_имя:
        n = 0
        for р in e.execute("SELECT inn, %s AS nm FROM base_ref" % поле_имя):
            н = норм(р["nm"])
            if len(н) >= 3:
                доп_имя.setdefault(н, []).append({"inn": р["inn"], "name": р["nm"],
                                                  "region": None, "revenue_rub": None,
                                                  "division": None})
            n += 1
        print("base_ref: %d строк, имён %d" % (n, len(доп_имя)))
except Exception as ex:
    print("base_ref недоступен: %s" % str(ex)[:120])

# --- сопоставление ---
итог = []
ст = {"домен": 0, "имя": 0, "имя_base_ref": 0, "неоднозначно": 0, "нет": 0}
for u in уч:
    почта = u["email"]
    домен = почта.split("@")[-1]
    зап = dict(u)
    зап["домен"] = домен
    зап["публичный"] = домен in ПУБЛИЧНЫЕ
    зап["inn"] = None
    зап["как"] = None
    зап["kandidaty"] = []

    if not зап["публичный"]:
        канд = по_домену.get(домен) or []
        уник = {к["inn"]: к for к in канд}
        if len(уник) == 1:
            зап["inn"] = list(уник)[0]
            зап["как"] = "домен"
        elif len(уник) > 1:
            зап["kandidaty"] = [уник[i] for i in list(уник)[:5]]

    if not зап["inn"]:
        н = норм(u["компания"])
        канд = по_имени.get(н) or []
        уник = {к["inn"]: к for к in канд}
        if len(уник) == 1:
            зап["inn"] = list(уник)[0]
            зап["как"] = "имя"
        elif len(уник) > 1:
            # если несколько - пробуем сузить по домену почты
            сузили = [к for к in уник.values()
                      if not зап["публичный"] and домен in
                      {домен_сайта(x) for x in [к.get("site")] if x}]
            зап["kandidaty"] = list(уник.values())[:5]

    if not зап["inn"] and доп_имя:
        н = норм(u["компания"])
        уник = {к["inn"]: к for к in (доп_имя.get(н) or [])}
        if len(уник) == 1:
            зап["inn"] = list(уник)[0]
            зап["как"] = "имя_base_ref"
        elif len(уник) > 1 and not зап["kandidaty"]:
            зап["kandidaty"] = list(уник.values())[:5]

    if зап["inn"]:
        ст[зап["как"]] += 1
    elif зап["kandidaty"]:
        ст["неоднозначно"] += 1
    else:
        ст["нет"] += 1
    итог.append(зап)

путь = os.path.join(БАЗА, "vebinar_inn_rezultat.json")
io.open(путь, "w", encoding="utf-8").write(json.dumps(итог, ensure_ascii=False, indent=0))

print("\n=== ПЕРВЫЕ 12 БЕЗ ИНН ===")
показано = 0
for з in итог:
    if not з["inn"] and показано < 12:
        print("  %-28s | %-30s | канд %d"
              % (з["компания"][:28], з["email"][:30], len(з["kandidaty"])))
        показано += 1

print("\n=== СВОДКА ===")
print("  всего участников: %d" % len(итог))
for k in ("домен", "имя", "имя_base_ref", "неоднозначно", "нет"):
    print("  %-16s %4d" % (k, ст[k]))
print("  ИНН найден: %d" % sum(1 for з in итог if з["inn"]))
print("  файл: %s" % путь)
