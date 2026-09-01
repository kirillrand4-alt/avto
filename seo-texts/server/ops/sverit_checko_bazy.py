# -*- coding: utf-8 -*-
"""Проверка стыковки: правда ли собранные по Чеко ИНН отсутствуют в базах.

Берём образцы из agro-base.csv и ищем их в enrich.db и obzvon-index.db —
и точным совпадением, и без ведущих нулей, чтобы исключить ошибку склейки.
Сводка в конце.
"""
import csv
import io
import os
import sqlite3

CSV = r"C:\seostat\Parser2\data\agro-base.csv"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


инны = []
с_нулём = 0
with io.open(CSV, encoding="utf-8-sig", errors="replace", newline="") as ф:
    for р in csv.DictReader(ф, delimiter=";"):
        и = цифры(р.get("ИНН"))
        if и:
            инны.append(и)
            if и.startswith("0"):
                с_нулём += 1
всего = len(инны)
набор = set(инны)

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
enrich_точно, enrich_без_нулей = set(), set()
enrich_всего = 0
for (и,) in e.execute("SELECT inn FROM companies"):
    ц = цифры(и)
    if not ц:
        continue
    enrich_всего += 1
    enrich_точно.add(ц)
    enrich_без_нулей.add(ц.lstrip("0"))
e.close()

обзвон_точно = set()
путь_обзвон = r"C:\sender\obzvon-index.db"
обзвон_всего = 0
if os.path.exists(путь_обзвон):
    o = sqlite3.connect("file:%s?mode=ro" % путь_обзвон, uri=True, timeout=120)
    try:
        табл = [r[0] for r in o.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for т in ("obzvon", "companies", "firms"):
            if т in табл:
                поля = [r[1] for r in o.execute("PRAGMA table_info(%s)" % т)]
                поле = next((п for п in поля if п.lower() in ("inn", "инн")),
                            None)
                if поле:
                    for (и,) in o.execute("SELECT %s FROM %s" % (поле, т)):
                        ц = цифры(и)
                        if ц:
                            обзвон_точно.add(ц)
                    обзвон_всего = len(обзвон_точно)
                    break
    except Exception:                                          # noqa: BLE001
        pass
    o.close()

совпало_точно = набор & enrich_точно
совпало_без_нулей = {и for и in набор if и.lstrip("0") in enrich_без_нулей}
в_обзвоне = набор & обзвон_точно
нигде = набор - enrich_точно - обзвон_точно

образцы = инны[:6]
проверка = []
e2 = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                     timeout=120)
for и in образцы:
    р = e2.execute("SELECT name, division FROM companies WHERE inn=?",
                   (и,)).fetchone()
    проверка.append((и, "есть: %s" % (р[0][:30] if р else "") if р else "НЕТ"))
e2.close()

print("=" * 66)
print("=== СВОДКА: СТЫКОВКА ЧЕКО С БАЗАМИ ===")
print("ИНН в файле сбора:            %8d (уникальных %d)" % (всего, len(набор)))
print("   из них с ведущим нулём:    %8d" % с_нулём)
print("компаний в enrich.db:         %8d" % enrich_всего)
print("компаний в obzvon-index.db:   %8d" % обзвон_всего)
print("")
print("совпало с enrich точно:       %8d" % len(совпало_точно))
print("совпало без ведущих нулей:    %8d  (если больше точного — беда склейки)"
      % len(совпало_без_нулей))
print("нашлось в базе обзвона:       %8d" % len(в_обзвоне))
print("НЕТ НИ В ОДНОЙ БАЗЕ:          %8d" % len(нигде))
print("")
print("=== ПРОВЕРКА ШЕСТИ ОБРАЗЦОВ В enrich.db ===")
for и, что in проверка:
    print("   %-14s %s" % (и, что))
