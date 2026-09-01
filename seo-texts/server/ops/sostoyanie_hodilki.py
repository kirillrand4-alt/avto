# -*- coding: utf-8 -*-
"""Жива ли ходилка checko_finansy: файл, прокси, журнал, что уже добыто."""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"
ПУТИ = [r"C:\sender\server\checko_finansy.py",
        r"C:\sender\_ops\checko_finansy.py",
        r"C:\sender\server\ops\checko_finansy.py"]

итог = []
for п in ПУТИ:
    итог.append("   %-44s %s" % (
        п, ("есть, %d Б, изменён %s" % (
            os.path.getsize(п),
            time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(п)))))
            if os.path.exists(п) else "НЕТ"))

# прокси
прокси_файл = None
for кор in (r"C:\sender", r"C:\seostat"):
    for путь, кат, файлы in os.walk(кор):
        кат[:] = [d for d in кат if d not in ("__pycache__", ".git", ".venv")]
        for имя in файлы:
            if имя == "dolphin-proxies.txt":
                прокси_файл = os.path.join(путь, имя)
                break
        if прокси_файл:
            break
    if прокси_файл:
        break

# журнал
строк, удач, сбоев = 0, 0, 0
последняя = None
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        строк += 1
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if z.get("сбой"):
            сбоев += 1
        else:
            удач += 1
        последняя = z

# что в базе
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
поля = [r[1] for r in e.execute("PRAGMA table_info(requisites)")]
всего_рек = e.execute("SELECT COUNT(*) FROM requisites").fetchone()[0]
с_огрн = e.execute(
    "SELECT COUNT(*) FROM requisites WHERE COALESCE(ogrn,'')<>''").fetchone()[0]
с_выручкой = 0
с_годом = 0
if "revenue_rub" in поля:
    с_выручкой = e.execute(
        "SELECT COUNT(*) FROM requisites "
        " WHERE COALESCE(revenue_rub,'') NOT IN ('','0')").fetchone()[0]
if "revenue_year" in поля:
    с_годом = e.execute(
        "SELECT COUNT(*) FROM requisites "
        " WHERE COALESCE(revenue_year,'') NOT IN ('','0')").fetchone()[0]
# и в companies
comp_выручка = e.execute(
    "SELECT COUNT(*) FROM companies "
    " WHERE revenue_rub IS NOT NULL AND revenue_rub > 0").fetchone()[0]
comp_всего = e.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
e.close()

print("=" * 68)
print("=== СВОДКА: ХОДИЛКА checko_finansy ===")
print("файл скрипта:")
for с in итог:
    print(с)
print("")
print("файл прокси: %s" % (прокси_файл or "НЕ НАЙДЕН"))
if прокси_файл:
    н = len([с for с in io.open(прокси_файл, encoding="utf-8",
                                errors="replace") if с.strip()])
    print("   строк в нём: %d" % н)
print("")
print("журнал %s" % ЖУРНАЛ)
print("   записей %d: удачных %d, сбоев %d" % (строк, удач, сбоев))
if последняя:
    print("   последняя: %s"
          % json.dumps({к: str(v)[:40] for к, v in последняя.items()},
                       ensure_ascii=False)[:240])
if os.path.exists(ЖУРНАЛ):
    print("   изменён %s" % time.strftime(
        "%d.%m %H:%M", time.localtime(os.path.getmtime(ЖУРНАЛ))))
print("")
print("таблица requisites: строк %d, из них с ОГРН %d" % (всего_рек, с_огрн))
print("   с выручкой:      %d" % с_выручкой)
print("   с годом отчёта:  %d" % с_годом)
print("")
print("для сравнения, companies: %d строк, выручка > 0 у %d"
      % (comp_всего, comp_выручка))
