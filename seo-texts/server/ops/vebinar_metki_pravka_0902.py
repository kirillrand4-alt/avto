# -*- coding: utf-8 -*-
"""Добавить меткам пяти компаний направление meyer: было «kc», станет
«kc+meyer». Добавление, а не замена: компрессорное направление сохраняется,
индекс читает метку через split('+'). Старые значения печатаем для отката.

argv: проба | делать
"""
import datetime as dt
import io
import json
import os
import sqlite3
import sys

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
ИНН = ["9726039928", "9724209420", "9705211462", "7713601938", "5321001735"]
ПУТЬ = r"C:\sender\obzvon-index.db"

c = sqlite3.connect(ПУТЬ)
c.row_factory = sqlite3.Row
было = {}
for р in c.execute("SELECT inn, division, name_short FROM obzvon WHERE inn IN (%s)"
                   % ",".join("?" * len(ИНН)), ИНН):
    было[р["inn"]] = (р["division"], р["name_short"])

print("=== СЕЙЧАС ===")
for inn in ИНН:
    д, н = было.get(inn, ("НЕТ СТРОКИ", ""))
    print("  %-12s %-8s %s" % (inn, д, str(н)[:44]))

нужно = [i for i in ИНН if было.get(i) and "meyer" not in (было[i][0] or "")]
print("\nк правке: %d из %d" % (len(нужно), len(ИНН)))

if not ДЕЛАТЬ:
    for i in нужно:
        print("  %s: «%s» -> «%s+meyer»" % (i, было[i][0], было[i][0]))
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

откат = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "vebinar_metki_otkat.json")
io.open(откат, "w", encoding="utf-8").write(json.dumps(
    {i: было[i][0] for i in нужно}, ensure_ascii=False))
print("файл отката: %s" % откат)

n = 0
for i in нужно:
    n += c.execute("UPDATE obzvon SET division=? WHERE inn=? AND division=?",
                   ("%s+meyer" % было[i][0], i, было[i][0])).rowcount
c.commit()
print("обновлено строк: %d" % n)

print("\n=== СТАЛО ===")
for р in c.execute("SELECT inn, division FROM obzvon WHERE inn IN (%s)"
                   % ",".join("?" * len(ИНН)), ИНН):
    print("  %-12s %s" % (р["inn"], р["division"]))
print("\nвсего меток в индексе:")
for р in c.execute("SELECT division, COUNT(*) n FROM obzvon GROUP BY division"):
    print("  %-12s %d" % (р["division"], р["n"]))
