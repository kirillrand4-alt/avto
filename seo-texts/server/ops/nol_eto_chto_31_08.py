# -*- coding: utf-8 -*-
"""Только чтение: revenue_rub = 0 — это настоящий ноль или «нет данных»?"""
import sqlite3
from collections import Counter

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row

print("=== companies: распределение revenue_rub ===")
всего = e.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
нулей = e.execute("SELECT COUNT(*) FROM companies WHERE revenue_rub=0").fetchone()[0]
нулл = e.execute("SELECT COUNT(*) FROM companies WHERE revenue_rub IS NULL").fetchone()[0]
плюс = e.execute("SELECT COUNT(*) FROM companies WHERE revenue_rub>0").fetchone()[0]
print("  всего компаний   : %d" % всего)
print("  revenue_rub > 0  : %d" % плюс)
print("  revenue_rub = 0  : %d" % нулей)
print("  revenue_rub NULL : %d" % нулл)

print("\n=== у нулей заполнен ли revenue_year ===")
for р in e.execute("SELECT CASE WHEN revenue_year IS NULL OR revenue_year='' "
                   " THEN 'год ПУСТ' ELSE 'год есть' END г, COUNT(*) n"
                   " FROM companies WHERE revenue_rub=0 GROUP BY г"):
    print("  нули: %-10s %d" % (р["г"], р["n"]))
for р in e.execute("SELECT CASE WHEN revenue_year IS NULL OR revenue_year='' "
                   " THEN 'год ПУСТ' ELSE 'год есть' END г, COUNT(*) n"
                   " FROM companies WHERE revenue_rub>0 GROUP BY г"):
    print("  >0  : %-10s %d" % (р["г"], р["n"]))

print("\n=== СВЕРКА: те самые ИНН из списка на снятие с 0.0 ===")
инны = ("2319057492", "3905604036", "7804633768", "9726019294",
        "2311300770", "7604273613")
for i in инны:
    стр = ["ИНН %s" % i]
    for р in e.execute("SELECT name, revenue_rub, revenue_year FROM companies"
                       " WHERE inn=?", (i,)):
        стр.append("companies: rev=%s год=%s | %s"
                   % (р["revenue_rub"], р["revenue_year"], str(р["name"])[:30]))
    for таб, кол in (("base_ref", "revenue"), ("requisites", "revenue_rub")):
        try:
            for р in e.execute("SELECT %s v FROM %s WHERE inn=?" % (кол, таб), (i,)):
                стр.append("%s: %s" % (таб, р["v"]))
        except Exception:
            pass
    print("  " + " || ".join(стр))

print("\n=== ЕСТЬ ЛИ У НУЛЕЙ ВЫРУЧКА В ДРУГИХ ТАБЛИЦАХ ===")
for таб, кол in (("base_ref", "revenue"), ("requisites", "revenue_rub")):
    try:
        n = e.execute(
            "SELECT COUNT(*) FROM companies c JOIN %s t ON t.inn=c.inn"
            " WHERE c.revenue_rub=0 AND t.%s IS NOT NULL AND CAST(t.%s AS REAL)>0"
            % (таб, кол, кол)).fetchone()[0]
        print("  нулей в companies, у кого в %s выручка > 0: %d" % (таб, n))
    except Exception as ex:
        print("  %s: %s" % (таб, str(ex)[:70]))

print("\n=== ИТОГ ===")
print("  если у нулей год пуст, а у положительных заполнен - ноль значит «нет данных»")
