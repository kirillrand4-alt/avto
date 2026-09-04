# -*- coding: utf-8 -*-
"""Только чтение: сколько компаний под зерновыми ОКВЭДами и как помечены."""
import sqlite3

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row
мейер = {р["inn"] for р in o.execute("SELECT inn FROM obzvon WHERE division"
                                     " LIKE '%meyer%'")}
все_обз = {р["inn"]: р["division"] for р in o.execute(
    "SELECT inn, division FROM obzvon")}

коды = ("01.11", "01.1", "01.61", "01.63", "10.61", "10.62", "52.10.3", "46.21")
print("%-9s %-44s %6s %6s %6s %6s %6s"
      % ("код", "название", "всего", "голых", "meyer", "30млн+", "готовы"))
for к in коды:
    ряды = list(e.execute(
        "SELECT inn, okved, revenue_rub, site, activity FROM companies"
        " WHERE okved LIKE ?", (к + " %",)))
    если = [р for р in ряды
            if not (р["site"] or "").strip()
            and len((р["activity"] or "").strip()) < 15]
    м = [р for р in если if р["inn"] in мейер]
    б = [р for р in м if (р["revenue_rub"] or 0) >= 30_000_000]
    имя = (ряды[0]["okved"][len(к):].strip()[:44] if ряды else "нет такого кода")
    print("%-9s %-44s %6d %6d %6d %6d" % (к, имя, len(ряды), len(если), len(м), len(б)))

print("\n=== КАК ПОМЕЧЕНЫ КОМПАНИИ 01.11 В БАЗЕ ОБЗВОНА ===")
гр = {}
for р in e.execute("SELECT inn FROM companies WHERE okved LIKE '01.11 %'"):
    д = все_обз.get(р["inn"])
    гр[str(д)] = гр.get(str(д), 0) + 1
for д, n in sorted(гр.items(), key=lambda x: -x[1]):
    print("  %-14s %d" % (д, n))

print("\n=== ПРИМЕРЫ КОМПАНИЙ 01.11 С ВЫРУЧКОЙ ОТ 30 МЛН ===")
n = 0
for р in e.execute("SELECT inn, name, revenue_rub, region, site FROM companies"
                   " WHERE okved LIKE '01.11 %' AND revenue_rub>=30000000"
                   " ORDER BY revenue_rub DESC"):
    if n >= 8:
        break
    print("  %-12s %-34s %6.0f млн  %s  сайт=%s"
          % (р["inn"], str(р["name"])[:34], (р["revenue_rub"] or 0) / 1e6,
             str(р["region"])[:16], (р["site"] or "нет")[:20]))
    n += 1
