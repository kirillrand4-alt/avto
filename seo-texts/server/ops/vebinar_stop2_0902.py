# -*- coding: utf-8 -*-
"""1) Сужаем неоднозначные ИНН по нашему справочнику и домену почты.
2) Повторный прогон 230 участников по стоп-листу сделок.
Пишем vebinar_inn_rezultat.json и vebinar_stop_rezultat.json."""
import io
import json
import os
import re
import sqlite3

БАЗА = os.path.dirname(os.path.abspath(__file__))
путь_инн = os.path.join(БАЗА, "vebinar_inn_rezultat.json")
уч = json.loads(io.open(путь_инн, encoding="utf-8").read())

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
ОПФ = re.compile(r"^(ооо|оао|зао|пао|ао|ип|нао|тд|гк|фгуп|гуп|муп|ано|кфх|спк)\b")
ПУБЛ = {"mail.ru", "gmail.com", "yandex.ru", "list.ru", "bk.ru", "inbox.ru",
        "ya.ru", "rambler.ru", "mail.com", "icloud.com", "yandex.com",
        "internet.ru", "narod.ru", "outlook.com", "hotmail.com", "yahoo.com"}


def норм(с):
    с = (с or "").lower().replace("ё", "е")
    с = re.sub(r"[\"'«»„“”`]", " ", с)
    с = re.sub(r"[^0-9a-zа-я ]+", " ", с)
    с = re.sub(r"\s+", " ", с).strip()
    б = None
    while б != с:
        б = с
        с = ОПФ.sub("", с).strip()
    return re.sub(r"\s+", "", с)


def домен_сайта(с):
    с = (с or "").strip().lower()
    if not с:
        return ""
    с = re.sub(r"^https?://", "", с).split("/")[0].split("?")[0]
    return с[4:] if с.startswith("www.") else с


# --- 1. сужение ---
сужено = 0
for u in уч:
    if u.get("inn"):
        continue
    канд = []
    for k in (u.get("dadata_kandidaty") or []):
        if k.get("inn"):
            канд.append(k["inn"])
    for k in (u.get("kandidaty") or []):
        if k.get("inn"):
            канд.append(k["inn"])
    канд = list(dict.fromkeys(канд))
    if not канд:
        continue
    q = "SELECT inn, name, site, cand_site FROM companies WHERE inn IN (%s)" \
        % ",".join("?" * len(канд))
    свои = list(e.execute(q, канд))
    д = u["домен"]
    if д not in ПУБЛ:
        по_сайту = [р for р in свои
                    if д in {домен_сайта(р["site"]), домен_сайта(р["cand_site"])}]
        if len(по_сайту) == 1:
            u["inn"] = по_сайту[0]["inn"]
            u["как"] = "сужено_по_домену"
            сужено += 1
            continue
    if len(свои) == 1:
        u["inn"] = свои[0]["inn"]
        u["как"] = "сужено_по_справочнику"
        сужено += 1

io.open(путь_инн, "w", encoding="utf-8").write(json.dumps(уч, ensure_ascii=False, indent=0))
print("сужено дополнительно: %d" % сужено)
print("ИНН всего: %d из %d" % (sum(1 for u in уч if u.get("inn")), len(уч)))

# --- 2. стоп-лист ---
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
инн_стоп, почты_стоп = {}, set()
for р in c.execute("SELECT scope, value, reason FROM suppression"):
    v = (р["value"] or "").strip().lower()
    if р["scope"] == "inn":
        инн_стоп[v] = р["reason"]
    elif р["scope"] == "email":
        почты_стоп.add(v)

имена_сделок, домены_сделок = {}, {}
сп = list(инн_стоп)
for i in range(0, len(сп), 800):
    кусок = сп[i:i + 800]
    q = ("SELECT inn, name, short_name, site, cand_site FROM companies"
         " WHERE inn IN (%s)" % ",".join("?" * len(кусок)))
    for р in e.execute(q, кусок):
        for поле in ("name", "short_name"):
            н = норм(р[поле])
            if len(н) >= 4:
                имена_сделок.setdefault(н, (р["inn"], р["name"]))
        for поле in ("site", "cand_site"):
            д = домен_сайта(р[поле])
            if д and "." in д:
                домены_сделок.setdefault(д, (р["inn"], р["name"]))

ОБЩИЕ = {"стандарт", "персона", "альтернатива", "холод", "перспектива", "континент",
         "слой", "звезда", "восток", "юг", "север", "заря", "успех", "лидер",
         "премиум", "престиж", "родник", "исток", "мир", "союз", "русь", "весна"}

совпало = []
for u in уч:
    пр, сила = [], "слабое"
    inn = (u.get("inn") or "").lower()
    if inn and inn in инн_стоп:
        пр.append("ИНН в стоп-листе (%s)" % инн_стоп[inn])
        сила = "точное"
    if u["email"] in почты_стоп:
        пр.append("почта в стоп-листе")
        сила = "точное"
    д = u["домен"]
    if д not in ПУБЛ and д in домены_сделок:
        пр.append("домен почты = сайт компании со сделкой: %s" % домены_сделок[д][1][:34])
        сила = "точное"
    н = норм(u["компания"])
    if len(н) >= 4 and н in имена_сделок:
        пр.append("название совпало со сделкой: %s" % имена_сделок[н][1][:34])
        if сила != "точное":
            сила = "слабое" if (н in ОБЩИЕ or len(н) <= 8) else "среднее"
    if пр:
        совпало.append({"строка": u["строка"], "email": u["email"],
                        "компания": u["компания"], "inn": u.get("inn"),
                        "сила": сила, "причины": пр})

io.open(os.path.join(БАЗА, "vebinar_stop_rezultat.json"), "w", encoding="utf-8").write(
    json.dumps(совпало, ensure_ascii=False, indent=0))

по_силе = {}
for з in совпало:
    по_силе[з["сила"]] = по_силе.get(з["сила"], 0) + 1

print("\n=== СЛАБЫЕ СОВПАДЕНИЯ (только по названию, имя типовое) ===")
for з in совпало:
    if з["сила"] == "слабое":
        print("  стр.%-4s %-26s %-28s %s"
              % (з["строка"], з["компания"][:26], з["email"][:28], з["причины"][0][:44]))

print("\n=== СВОДКА ===")
print("  участников: %d" % len(уч))
print("  ИНН известен: %d" % sum(1 for u in уч if u.get("inn")))
print("  под стоп-листом: %d (%s)"
      % (len(совпало), ", ".join("%s %d" % (k, v) for k, v in sorted(по_силе.items()))))
print("  остаётся: %d" % (len(уч) - len(совпало)))
