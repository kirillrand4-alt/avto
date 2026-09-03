# -*- coding: utf-8 -*-
"""Правда ли у компаний нет сайта, или разбор его не видит. Плюс баланс.

Берём компании свежего сбора, у которых в журнале ходилки сайта нет,
тянем их страницу контактов теми же прокси и смотрим ДВУМЯ способами:
разбором самой ходилки и грубым поиском ссылок в HTML.
"""
import io
import json
import os
import re
import sqlite3
import sys
import urllib.request

sys.path.insert(0, r"C:\sender\server")
sys.path.insert(0, r"C:\sender\server\ops")
import requests                                                # noqa: E402

# --- баланс --------------------------------------------------------------
баланс = "нет ключей"
user = os.environ.get("XMLRIVER_USER", "")
key = os.environ.get("XMLRIVER_KEY", "")
if user and key:
    try:
        о = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        з = urllib.request.Request(
            "http://xmlriver.com/api/get_balance/?user=%s&key=%s" % (user, key))
        баланс = о.open(з, timeout=30).read().decode("utf-8", "replace")[:120]
    except Exception as ex:                                    # noqa: BLE001
        баланс = "не спросился: %s" % str(ex)[:80]

# --- разбор из самой ходилки --------------------------------------------
import importlib.util                                          # noqa: E402
спец = importlib.util.spec_from_file_location(
    "chf", r"C:\sender\_ops\checko_finansy.py")
мод = importlib.util.module_from_spec(спец)
разобрать_контакты = None
try:
    sys.argv = ["chf"]
    спец.loader.exec_module(мод)
    разобрать_контакты = getattr(мод, "разобрать_контакты", None)
except Exception as ex:                                        # noqa: BLE001
    print("модуль ходилки не загрузился: %s" % str(ex)[:120])

# --- компании без сайта из свежего сбора ---------------------------------
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
свежие = {}
for и, о, н in c.execute(
        "SELECT inn, ogrn, name_short FROM requisites "
        " WHERE src='checko-sbor-agro' AND COALESCE(ogrn,'')<>''"):
    свежие[str(и)] = (str(о), str(н or ""))
c.close()

без_сайта = []
for с in io.open(r"C:\sender\server\checko_finansy.jsonl", encoding="utf-8",
                 errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if z.get("сбой"):
        continue
    и = str(z.get("inn") or "")
    if и in свежие and not str(z.get("site_checko") or "").strip():
        без_сайта.append(и)
    if len(без_сайта) >= 5:
        break

прокси = None
with open(r"C:\sender\proxies-mobile.txt", encoding="utf-8",
          errors="replace") as ф:
    for l in ф.read().splitlines():
        if l.strip() and not l.startswith("#"):
            прокси = l.strip()
            break

итоги = []
for и in без_сайта:
    огрн, имя = свежие[и]
    try:
        r = requests.get("https://checko.ru/company/%s/contacts" % огрн,
                         proxies={"http": прокси, "https": прокси},
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0;"
                                                " Win64; x64) AppleWebKit/537.36"},
                         timeout=25)
        html = r.text or ""
    except Exception as ex:                                    # noqa: BLE001
        итоги.append("%s %-26s ОШИБКА %s" % (и, имя[:26], str(ex)[:40]))
        continue
    разбор = {}
    if разобрать_контакты:
        try:
            разбор = разобрать_контакты(html) or {}
        except Exception as ex:                                # noqa: BLE001
            разбор = {"ошибка": str(ex)[:50]}
    # грубый поиск: внешние ссылки, не соцсети и не чеко
    ссылки = set()
    for м in re.finditer(r'href="(https?://([^"/]+))', html):
        д = м.group(2).lower()
        if any(x in д for x in ("checko.ru", "vk.com", "ok.ru", "t.me",
                                "facebook", "instagram", "youtube",
                                "yandex", "google", "mail.ru", "wa.me",
                                "gosuslugi", "nalog.ru", "rusprofile")):
            continue
        ссылки.add(д)
    итоги.append("%s %-26s код %s | разбор сайта: %-18s | ссылок в HTML: %s"
                 % (и, имя[:26], r.status_code,
                    str(разбор.get("site_checko") or "—")[:18],
                    ", ".join(sorted(ссылки)[:3]) or "нет"))

print("=" * 88)
print("=== СВОДКА: ПРАВДА ЛИ НЕТ САЙТОВ ===")
print("баланс XMLRiver: %s" % баланс)
print("разбор ходилки загружен: %s" % ("да" if разобрать_контакты else "НЕТ"))
print("")
for с in итоги:
    print("   " + с)
