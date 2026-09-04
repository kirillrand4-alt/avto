# -*- coding: utf-8 -*-
"""Только чтение: нынешний запасной путь без фактов и полный расклад ОКВЭД."""
import inspect
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
import sender.ai_letter as A  # noqa: E402

исх = inspect.getsource(A)
for сл in ("без фактов", "фактов нет"):
    н = исх.lower().find(сл)
    if н > 0:
        print("=== КОНТЕКСТ «%s» ===" % сл)
        print(исх[max(0, н - 700):н + 700])
        print()

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row
мейер = {р["inn"] for р in o.execute("SELECT inn FROM obzvon WHERE division"
                                     " LIKE '%meyer%'")}
гр = {}
for р in e.execute("SELECT inn, okved, revenue_rub FROM companies"
                   " WHERE okved IS NOT NULL AND okved<>''"
                   " AND (activity IS NULL OR LENGTH(activity)<15)"
                   " AND (site IS NULL OR site='')"):
    if р["inn"] not in мейер:
        continue
    к = str(р["okved"])
    код = к.split()[0] if к else "?"
    д = гр.setdefault(код, {"n": 0, "богатых": 0, "имя": к[:52]})
    д["n"] += 1
    if (р["revenue_rub"] or 0) >= 30_000_000:
        д["богатых"] += 1

всего = sum(д["n"] for д in гр.values())
богатых = sum(д["богатых"] for д in гр.values())
print("=== ГОЛЫЕ MEYER-КОМПАНИИ: %d, из них с выручкой от 30 млн: %d ==="
      % (всего, богатых))
топ = sorted(гр.items(), key=lambda x: -x[1]["богатых"])
накопл = 0
print("\n  %-8s %-46s %6s %6s %6s" % ("код", "название", "всего", "30млн+", "накопл"))
for код, д in топ[:24]:
    накопл += д["богатых"]
    print("  %-8s %-46s %6d %6d %6d"
          % (код, д["имя"][6:52].strip(), д["n"], д["богатых"], накопл))
print("\n  первые 24 кода покрывают %d из %d богатых (%.0f%%)"
      % (накопл, богатых, 100.0 * накопл / max(1, богатых)))
