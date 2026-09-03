# -*- coding: utf-8 -*-
"""Сколько XMLRiver нужно ТОЛЬКО под мейеровские компании свежего сбора.

Отделяем свежий агро-сбор (src='checko-sbor-agro') от старых строк базы:
ходилка первые сутки шла по старым, и в журнале они вперемешку. Нефтяники,
попавшие в верхушку, — как раз оттуда.
"""
import io
import json
import os
import re
import sqlite3
from collections import Counter

ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"

# кто из свежего сбора
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
свежие = {r[0] for r in c.execute(
    "SELECT inn FROM requisites WHERE src='checko-sbor-agro'")}
коды = {}
for и, к in c.execute(
        "SELECT inn, okved_main FROM requisites WHERE src='checko-sbor-agro'"):
    коды[str(и)] = str(к or "")
c.close()

разрез = Counter()
без_сайта_мейер = []
с_сайтом_мейер = 0
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
    и = str(z.get("inn") or "")
    свой = и in свежие
    сайт = str(z.get("site_checko") or "").strip()
    try:
        выр = int(str(z.get("revenue_rub") or "0") or 0)
    except ValueError:
        выр = 0
    разрез["свежий сбор" if свой else "старая база"] += 1
    if not свой:
        continue
    if сайт:
        с_сайтом_мейер += 1
        continue
    if выр >= 100_000_000:
        без_сайта_мейер.append(("от 100 млн", и))
    elif выр >= 30_000_000:
        без_сайта_мейер.append(("30-100 млн", и))
    elif выр > 0:
        без_сайта_мейер.append(("ниже 30 млн", и))
    else:
        без_сайта_мейер.append(("выручка не добыта", и))

по_полосам = Counter(п for п, _ in без_сайта_мейер)
от30 = по_полосам["от 100 млн"] + по_полосам["30-100 млн"]

print("=" * 76)
print("=== СВОДКА: XMLRIVER ТОЛЬКО ПОД MEYER ===")
print("обработано ходилкой: %s" % dict(разрез))
print("")
print("СВЕЖИЙ АГРО-СБОР (это и есть мейеровский пул):")
print("   сайт Чеко отдал:            %7d" % с_сайтом_мейер)
print("   БЕЗ САЙТА — нужен поиск:    %7d" % len(без_сайта_мейер))
for к, в in по_полосам.most_common():
    print("      %-22s %7d" % (к, в))
print("")
print("=== СКОЛЬКО ЗАПРОСОВ XMLRIVER ===")
print("   первая очередь (от 30 млн): %7d запросов" % от30)
print("   вся мейеровская выборка:    %7d запросов" % len(без_сайта_мейер))
print("")
print("Один запрос на компанию — так работает find_site_via_xmlriver.")
print("Ходилка ещё идёт: пройдено 20780 из 26760, остаток добавит целей.")
