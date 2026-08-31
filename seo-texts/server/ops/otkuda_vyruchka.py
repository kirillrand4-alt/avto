# -*- coding: utf-8 -*-
"""Где на самом деле лежит выручка: companies.revenue_rub или requisites."""
import sqlite3

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


print("=== ИСТОЧНИКИ ВЫРУЧКИ В ОБОГАЩЕНИИ ===")
n = e.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
c1 = e.execute("SELECT COUNT(*) FROM companies WHERE revenue_rub IS NOT NULL"
               "   AND revenue_rub<>0").fetchone()[0]
print("   companies: строк %d, с ненулевой revenue_rub %d (%.1f%%)"
      % (n, c1, 100.0 * c1 / n))
r1 = e.execute("SELECT COUNT(*) FROM requisites WHERE COALESCE(revenue_rub,'')"
               " NOT IN ('','0')").fetchone()[0]
rn = e.execute("SELECT COUNT(*) FROM requisites").fetchone()[0]
print("   requisites: строк %d, с непустой revenue_rub %d" % (rn, r1))

таблицы = [r[0] for r in e.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
print("\n   где ещё есть колонка про выручку:")
for т in таблицы:
    столбцы = [x[1] for x in e.execute("PRAGMA table_info(%s)" % т)]
    свои = [c for c in столбцы if "revenue" in c.lower() or "vyruch" in c.lower()]
    if свои:
        k = e.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        print("      %-14s %-24s строк %d" % (т, ",".join(свои), k))

print("\n=== МЕЙЕРОВСКИЕ: ВЫРУЧКА ПО ДВУМ ИСТОЧНИКАМ ===")
мейер = {}
for r in e.execute("SELECT inn, revenue_rub FROM companies"
                   " WHERE division LIKE '%meyer%'"):
    мейер[цифры(r["inn"])] = r["revenue_rub"]
print("   мейеровских компаний: %d" % len(мейер))
нет_в_companies = {и for и, v in мейер.items() if v is None or int(v or 0) == 0}
print("   выручки нет в companies: %d (%.1f%%)"
      % (len(нет_в_companies), 100.0 * len(нет_в_companies) / len(мейер)))

нашлось = 0
списком = list(нет_в_companies)
for i in range(0, len(списком), 500):
    часть = списком[i:i + 500]
    for r in e.execute("SELECT inn, revenue_rub FROM requisites"
                       " WHERE inn IN (%s)" % ",".join("?" * len(часть)), часть):
        v = str(r["revenue_rub"] or "").strip()
        if v and v not in ("0", "None"):
            нашлось += 1
print("   из них выручка ЕСТЬ в requisites: %d" % нашлось)
print("   остаётся неизвестной после сверки двух таблиц: %d"
      % (len(нет_в_companies) - нашлось))

print("\n=== ОБРАЗЕЦ requisites.revenue_rub ===")
for r in e.execute("SELECT inn, revenue_rub, fin_god FROM requisites"
                   " WHERE COALESCE(revenue_rub,'') NOT IN ('','0') LIMIT 5"):
    print("   ИНН %s  выручка %r  год %r" % (r["inn"], r["revenue_rub"],
                                             r["fin_god"]))
e.close()
print("\n=== ИТОГ ===")
print("если выручка массово лежит в requisites, а я читал только companies —")
print("моя цифра «неизвестна у 3846» завышена, и права соседняя сессия.")
