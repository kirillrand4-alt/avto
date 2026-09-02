# -*- coding: utf-8 -*-
"""Добираем ИНН через DaData для тех, кого не нашли в справочнике.
Наружу уходят только названия компаний из файла участников; почты и имена
людей не отправляются. Результат дописываем в vebinar_inn_rezultat.json."""
import io
import json
import os
import re
import time
import urllib.request

БАЗА = os.path.dirname(os.path.abspath(__file__))
путь = os.path.join(БАЗА, "vebinar_inn_rezultat.json")
уч = json.loads(io.open(путь, encoding="utf-8").read())

ТОКЕН = os.environ.get("DADATA_TOKEN", "").strip()
if not ТОКЕН:
    raise SystemExit("нет DADATA_TOKEN в окружении")

URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"
ОПФ = re.compile(r"^(ооо|оао|зао|пао|ао|ип|нао|тд|гк|фгуп|гуп|муп|ано|кфх|спк)\b")
МУСОР = {"физлицо", "физлицо", "физ лицо", "нет", "-", "+7", "я", "себя"}


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


def спросить(имя):
    тело = json.dumps({"query": имя, "count": 5,
                       "status": ["ACTIVE"]}).encode("utf-8")
    зпр = urllib.request.Request(URL, data=тело, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "Authorization": "Token " + ТОКЕН})
    with urllib.request.urlopen(зпр, timeout=25) as r:
        return json.loads(r.read().decode("utf-8")).get("suggestions") or []


ст = {"точно": 0, "один": 0, "много": 0, "пусто": 0, "пропуск": 0, "ошибка": 0}
for u in уч:
    if u.get("inn"):
        continue
    имя = (u.get("компания") or "").strip()
    н = норм(имя)
    if len(н) < 3 or н in МУСОР or имя.isdigit():
        # в поле «компания» бывает ИНН - берём как есть
        цифры = re.sub(r"\D", "", имя)
        if len(цифры) in (10, 12):
            u["inn"] = цифры
            u["как"] = "инн_в_поле"
            ст["точно"] += 1
        else:
            ст["пропуск"] += 1
        continue
    try:
        подск = спросить(имя)
    except Exception as ex:
        u["dadata_oshibka"] = str(ex)[:80]
        ст["ошибка"] += 1
        time.sleep(0.4)
        continue
    time.sleep(0.12)
    if not подск:
        ст["пусто"] += 1
        continue
    точные = [п for п in подск
              if норм(п["data"].get("name", {}).get("short_with_opf")) == н
              or норм(п["data"].get("name", {}).get("full_with_opf")) == н]
    if len(точные) == 1:
        д = точные[0]["data"]
        u["inn"] = д.get("inn")
        u["как"] = "dadata_точно"
        u["dadata_name"] = точные[0].get("value")
        ст["точно"] += 1
    elif len(подск) == 1:
        д = подск[0]["data"]
        u["inn"] = д.get("inn")
        u["как"] = "dadata_один"
        u["dadata_name"] = подск[0].get("value")
        ст["один"] += 1
    else:
        u["dadata_kandidaty"] = [{"inn": п["data"].get("inn"), "name": п.get("value")}
                                 for п in подск[:4]]
        ст["много"] += 1

io.open(путь, "w", encoding="utf-8").write(json.dumps(уч, ensure_ascii=False, indent=0))

print("=== ПРИМЕРЫ НЕОДНОЗНАЧНЫХ (первые 10) ===")
n = 0
for u in уч:
    if u.get("dadata_kandidaty") and n < 10:
        print("  %-26s -> %s" % (u["компания"][:26],
                                 " | ".join("%s %s" % (k["inn"], str(k["name"])[:26])
                                            for k in u["dadata_kandidaty"][:2])))
        n += 1

print("\n=== СВОДКА DaData ===")
for k in ("точно", "один", "много", "пусто", "пропуск", "ошибка"):
    print("  %-10s %4d" % (k, ст[k]))
print("  ИНН всего теперь: %d из %d" % (sum(1 for u in уч if u.get("inn")), len(уч)))
