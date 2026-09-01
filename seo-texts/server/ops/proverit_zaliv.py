# -*- coding: utf-8 -*-
"""Сколько строк реально легло в requisites и что с ними дальше."""
import io
import json
import os
import sqlite3
from collections import Counter

БАЗА = r"C:\sender\enrich.db"
ЖУРНАЛ = r"C:\sender\_ops\zaliv-requisites.jsonl"

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=180)
всего = c.execute("SELECT COUNT(*) FROM requisites").fetchone()[0]
наших = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro'").fetchone()[0]
с_огрн = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE COALESCE(ogrn,'')<>''").fetchone()[0]
без_выручки = c.execute(
    "SELECT COUNT(*) FROM requisites "
    " WHERE COALESCE(ogrn,'')<>'' AND COALESCE(revenue_rub,'') IN ('','0')"
).fetchone()[0]
по_кодам = Counter()
for к, н in c.execute(
        "SELECT okved_main, COUNT(*) FROM requisites "
        " WHERE src='checko-sbor-agro' GROUP BY okved_main"):
    по_кодам[к or "?"] = н
c.close()

# журнал заливки
записи = []
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if с:
            записи.append(с)

print("=" * 68)
print("=== СВОДКА: ЧТО ЛЕГЛО В requisites ===")
print("строк в таблице всего:            %7d" % всего)
print("из них с меткой checko-sbor-agro: %7d" % наших)
print("строк с ОГРН (их видит ходилка):  %7d" % с_огрн)
print("   из них выручки ещё нет:        %7d   <- работа для ходилки"
      % без_выручки)
print("")
print("ЛЕГЛО ПО КОДАМ:")
for к, н in по_кодам.most_common():
    print("   %-10s %7d" % (к, н))
print("")
print("журнал заливки: %d записей" % len(записи))
for с in записи[-4:]:
    print("   " + с[:200])
