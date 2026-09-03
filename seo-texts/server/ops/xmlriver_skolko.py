# -*- coding: utf-8 -*-
"""Сколько надо XMLRiver на новые компании: расход, баланс, объём работы.

Секреты (ключ, user id) не печатаем.
"""
import io
import json
import os
import re
import sqlite3
import urllib.request

# --- где используется ----------------------------------------------------
места = []
for корень in (r"C:\sender", r"C:\seostat\Parser2"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", ".git", ".venv",
                                              "node_modules", "dist",
                                              "razobrano", "gotovo",
                                              "pagecache", "drop-storage")]
        for имя in файлы:
            if not имя.endswith((".py", ".md", ".env", ".yaml", ".yml")):
                continue
            п = os.path.join(путь, имя)
            try:
                if os.path.getsize(п) > 400000:
                    continue
                т = io.open(п, encoding="utf-8", errors="replace").read()
            except Exception:                                  # noqa: BLE001
                continue
            if re.search(r"xmlriver|xml_river|XMLRIVER", т, re.I):
                for м in re.finditer(r"^.{0,110}xmlriver.{0,110}$", т,
                                     re.I | re.M):
                    с = м.group(0).strip()
                    с = re.sub(r"(key|user|token)\s*=\s*['\"]?[\w-]{4,}",
                               r"\1=<скрыто>", с, flags=re.I)
                    места.append("%s| %s" % (os.path.basename(п), с[:150]))
                    break
        if len(места) > 40:
            break

# --- переменные окружения ------------------------------------------------
окружение = [к for к in os.environ if "river" in к.lower() or "xml" in к.lower()]

# --- баланс --------------------------------------------------------------
баланс = "не спрашивали"
user = os.environ.get("XMLRIVER_USER") or os.environ.get("XML_RIVER_USER")
key = os.environ.get("XMLRIVER_KEY") or os.environ.get("XML_RIVER_KEY")
if user and key:
    try:
        о = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        з = urllib.request.Request(
            "http://xmlriver.com/api/get_balance/?user=%s&key=%s" % (user, key))
        баланс = о.open(з, timeout=30).read().decode("utf-8", "replace")[:200]
    except Exception as ex:                                    # noqa: BLE001
        баланс = "запрос не прошёл: %s" % str(ex)[:90]

# --- объём работы: у кого нет сайта --------------------------------------
ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"
всего, с_сайтом, без_сайта, от30_без_сайта = 0, 0, 0, 0
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if z.get("сбой"):
        continue
    всего += 1
    сайт = str(z.get("site_checko") or "").strip()
    try:
        выр = int(str(z.get("revenue_rub") or "0") or 0)
    except ValueError:
        выр = 0
    if сайт:
        с_сайтом += 1
    else:
        без_сайта += 1
        if выр >= 30_000_000:
            от30_без_сайта += 1

print("=" * 76)
print("=== СВОДКА: XMLRIVER ===")
print("переменные окружения: %s" % (окружение or "нет ни одной"))
print("баланс: %s" % баланс)
print("")
print("где используется:")
for с in list(dict.fromkeys(места))[:12]:
    print("   " + с)
print("")
print("=== ОБЪЁМ РАБОТЫ ПО ЖУРНАЛУ ХОДИЛКИ ===")
print("   компаний обработано:        %7d" % всего)
print("   у скольких Чеко дал сайт:   %7d" % с_сайтом)
print("   БЕЗ САЙТА (нужен поиск):    %7d" % без_сайта)
print("   из них от 30 млн:           %7d   <- им искать в первую очередь"
      % от30_без_сайта)
