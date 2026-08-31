# -*- coding: utf-8 -*-
"""NULL или 0: вот где расходятся наши цифры по «неизвестной выручке»."""
import sqlite3

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
print("=== МЕЙЕРОВСКИЕ: КАК ЗАПИСАНА ОТСУТСТВУЮЩАЯ ВЫРУЧКА ===")
for метка, условие in (
        ("revenue_rub IS NULL", "revenue_rub IS NULL"),
        ("revenue_rub = 0", "revenue_rub = 0"),
        ("revenue_rub > 0", "revenue_rub > 0"),
        ("revenue_rub >= 30 млн", "revenue_rub >= 30000000")):
    n = e.execute("SELECT COUNT(*) FROM companies"
                  " WHERE division LIKE '%meyer%' AND " + условие).fetchone()[0]
    print("   %-24s %7d" % (метка, n))

print("\n=== ПО ВСЕЙ БАЗЕ ===")
for метка, условие in (("IS NULL", "revenue_rub IS NULL"),
                       ("= 0", "revenue_rub = 0"),
                       ("> 0", "revenue_rub > 0")):
    n = e.execute("SELECT COUNT(*) FROM companies WHERE "
                  + условие).fetchone()[0]
    print("   %-10s %7d" % (метка, n))

print("\n=== ЕСТЬ ЛИ У НУЛЕЙ ПРИЗНАКИ ЖИВОЙ ФИРМЫ ===")
r = e.execute(
    "SELECT COUNT(*) всего,"
    "  SUM(CASE WHEN COALESCE(site,'')<>'' THEN 1 ELSE 0 END) с_сайтом,"
    "  SUM(CASE WHEN COALESCE(ogrn,'')<>'' THEN 1 ELSE 0 END) с_огрн,"
    "  SUM(CASE WHEN COALESCE(status_egrul,'')<>'' THEN 1 ELSE 0 END) со_статусом"
    "  FROM companies WHERE division LIKE '%meyer%' AND revenue_rub=0").fetchone()
print("   нулей: %d; из них с сайтом %d, с ОГРН %d, со статусом ЕГРЮЛ %d"
      % r)
r2 = e.execute(
    "SELECT COUNT(*) FROM companies WHERE division LIKE '%meyer%'"
    "   AND revenue_rub=0 AND COALESCE(revenue_year,'')<>''").fetchone()[0]
print("   у скольких нулей проставлен revenue_year: %d" % r2)
print("\n   примеры нулей:")
for r3 in e.execute("SELECT inn, name, revenue_rub, revenue_year, site"
                    "  FROM companies WHERE division LIKE '%meyer%'"
                    "   AND revenue_rub=0 LIMIT 5"):
    print("      %s %-30s rev=%r год=%r сайт=%s"
          % (r3[0], str(r3[1])[:30], r3[2], r3[3], r3[4]))
e.close()
print("\n=== ИТОГ ===")
print("если отсутствующая выручка записана НУЛЁМ, то «IS NULL» ловит единицы,")
print("а нули молча проваливают порог 30 млн — компания выбывает не потому,")
print("что мала, а потому что про неё нет данных.")
