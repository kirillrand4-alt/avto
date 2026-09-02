# -*- coding: utf-8 -*-
"""Только чтение. 1) есть ли на панели ключ DaData; 2) прогон 230 участников
по стоп-листу сделок: по ИНН, по домену почты, по названию компании."""
import io
import json
import os
import re
import sqlite3

БАЗА = os.path.dirname(os.path.abspath(__file__))
уч = json.loads(io.open(os.path.join(БАЗА, "vebinar_inn_rezultat.json"),
                        encoding="utf-8").read())

print("=== 1. КЛЮЧ DaData НА ПАНЕЛИ ===")
найдено = []
for корень in (r"C:\sender", r"C:\sender\server"):
    for имя in os.listdir(корень):
        п = os.path.join(корень, имя)
        if not os.path.isfile(п):
            continue
        if os.path.getsize(п) > 400000:
            continue
        if not имя.lower().endswith((".yaml", ".yml", ".env", ".json", ".ini", ".cfg")):
            continue
        try:
            т = io.open(п, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for м in re.finditer(r"(?i)(dadata|DADATA_\w+|checko|CHECKO_\w+)", т):
            найдено.append("%s: %s" % (имя, м.group(0)))
ун = sorted(set(найдено))
print("  упоминаний: %d" % len(ун))
for x in ун[:12]:
    print("    " + x)
есть_env = [k for k in os.environ if "DADATA" in k.upper() or "CHECKO" in k.upper()]
print("  в окружении службы: %s" % (", ".join(есть_env) or "нет"))

# --- 2. стоп-лист ---
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
инн_стоп = {}
для_почт = set()
домены_стоп = set()
for р in c.execute("SELECT scope, value, reason, source FROM suppression"):
    v = (р["value"] or "").strip().lower()
    if р["scope"] == "inn":
        инн_стоп[v] = (р["reason"], р["source"])
    elif р["scope"] == "email":
        для_почт.add(v)
    elif р["scope"] == "domain":
        домены_стоп.add(v)
print("\n=== 2. СТОП-ЛИСТ ===")
print("  инн %d | почт %d | доменов %d" % (len(инн_стоп), len(для_почт), len(домены_стоп)))

ОПФ = re.compile(r"^(ооо|оао|зао|пао|ао|ип|нао|тд|гк|фгуп|гуп|муп|ано|кфх|спк)\b")


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


# названия и сайты компаний, с которыми уже есть сделка
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
имена_сделок = {}
домены_сделок = {}
if инн_стоп:
    сп = list(инн_стоп)
    for i in range(0, len(сп), 800):
        кусок = сп[i:i + 800]
        q = "SELECT inn, name, short_name, site, cand_site FROM companies WHERE inn IN (%s)" \
            % ",".join("?" * len(кусок))
        for р in e.execute(q, кусок):
            for поле in ("name", "short_name"):
                н = норм(р[поле])
                if len(н) >= 4:
                    имена_сделок.setdefault(н, р["inn"])
            for поле in ("site", "cand_site"):
                д = домен_сайта(р[поле])
                if д and "." in д:
                    домены_сделок.setdefault(д, р["inn"])
print("  из них опознано в справочнике: имён %d, доменов %d"
      % (len(имена_сделок), len(домены_сделок)))

ПУБЛ = {"mail.ru", "gmail.com", "yandex.ru", "list.ru", "bk.ru", "inbox.ru",
        "ya.ru", "rambler.ru", "mail.com", "icloud.com", "yandex.com",
        "internet.ru", "narod.ru", "outlook.com", "hotmail.com", "yahoo.com"}

совпало = []
for u in уч:
    причины = []
    if u.get("inn") and u["inn"].lower() in инн_стоп:
        причины.append("инн:%s" % инн_стоп[u["inn"].lower()][0])
    if u["email"] in для_почт:
        причины.append("почта")
    д = u["домен"]
    if д in домены_стоп:
        причины.append("домен")
    if д not in ПУБЛ and д in домены_сделок:
        причины.append("сайт-сделки:%s" % домены_сделок[д])
    н = норм(u["компания"])
    if len(н) >= 4 and н in имена_сделок:
        причины.append("имя-сделки:%s" % имена_сделок[н])
    if причины:
        совпало.append((u, причины))

путь = os.path.join(БАЗА, "vebinar_stop_rezultat.json")
io.open(путь, "w", encoding="utf-8").write(json.dumps(
    [{"строка": u["строка"], "email": u["email"], "компания": u["компания"],
      "inn": u.get("inn"), "причины": пр} for u, пр in совпало],
    ensure_ascii=False, indent=0))

print("\n=== 3. ПОПАЛИ В СТОП-ЛИСТ ===")
for u, пр in совпало[:40]:
    print("  %-30s %-30s %s" % (u["компания"][:30], u["email"][:30], ",".join(пр)[:46]))

print("\n=== СВОДКА ===")
print("  участников: %d" % len(уч))
print("  под стоп-листом: %d" % len(совпало))
print("  остаётся к отправке: %d" % (len(уч) - len(совпало)))
print("  файл: %s" % путь)
