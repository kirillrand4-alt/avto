# -*- coding: utf-8 -*-
"""Только чтение: что генератор знает о компании и сколько компаний
живут на одном ОКВЭДе."""
import inspect
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
import sender.ai_letter as A  # noqa: E402

исх = inspect.getsource(A)
print("=== ЧТО ПОДАЁТСЯ В ПРОМПТ (поля карточки) ===")
for м in re.finditer(r"(activity|okved|site_facts|продукц|деятельн|факты)", исх):
    н = исх[:м.start()].count("\n")
    с = исх.splitlines()[н].strip()
    if с.startswith("#") or len(с) < 10:
        continue
    if any(k in с for k in ("=", "get(", "if ", "f\"", "'''", '"""')):
        print("  %s" % с[:104])

print("\n=== ЕСТЬ ЛИ ВЕТКА «ФАКТОВ НЕТ» ===")
for сл in ("нет фактов", "без фактов", "фактов нет", "activity_verified",
           "не удалось", "только оквэд", "okved_only"):
    k = исх.lower().count(сл.lower())
    if k:
        print("  «%s» встречается %d раз" % (сл, k))

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row

print("\n=== СКОЛЬКО КОМПАНИЙ ЖИВУТ НА ОДНОМ ОКВЭДЕ ===")
всего = e.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
сайт = e.execute("SELECT COUNT(*) FROM companies WHERE site IS NOT NULL"
                 " AND site<>''").fetchone()[0]
акт = e.execute("SELECT COUNT(*) FROM companies WHERE activity IS NOT NULL"
                " AND LENGTH(activity)>=15").fetchone()[0]
факты = e.execute("SELECT COUNT(DISTINCT inn) FROM site_facts").fetchone()[0]
окв = e.execute("SELECT COUNT(*) FROM companies WHERE okved IS NOT NULL"
                " AND okved<>''").fetchone()[0]
print("  компаний всего:            %d" % всего)
print("  с ОКВЭД:                   %d" % окв)
print("  с сайтом:                  %d" % сайт)
print("  с описанием деятельности:  %d" % акт)
print("  с разобранным паспортом:   %d" % факты)
голые = e.execute("SELECT COUNT(*) FROM companies WHERE okved IS NOT NULL"
                  " AND okved<>'' AND (activity IS NULL OR LENGTH(activity)<15)"
                  " AND (site IS NULL OR site='')").fetchone()[0]
print("  ТОЛЬКО ОКВЭД, без сайта и описания: %d" % голые)

print("\n=== ТОП ОКВЭД СРЕДИ ГОЛЫХ, ЧЬЁ НАПРАВЛЕНИЕ meyer ===")
мейер = {р["inn"] for р in o.execute("SELECT inn FROM obzvon WHERE division"
                                     " LIKE '%meyer%'")}
гр = {}
for р in e.execute("SELECT inn, okved FROM companies WHERE okved IS NOT NULL"
                   " AND okved<>'' AND (activity IS NULL OR LENGTH(activity)<15)"
                   " AND (site IS NULL OR site='')"):
    if р["inn"] in мейер:
        к = str(р["okved"])[:60]
        гр[к] = гр.get(к, 0) + 1
print("  таких компаний: %d" % sum(гр.values()))
for к, n in sorted(гр.items(), key=lambda x: -x[1])[:16]:
    print("    %-58s %d" % (к, n))
