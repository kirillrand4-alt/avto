# -*- coding: utf-8 -*-
"""Распределение выручки по всей базе обзвона: целиком и по направлениям."""
import sqlite3
import statistics
from collections import defaultdict

БД = r"C:\sender\obzvon-index.db"
c = sqlite3.connect("file:%s?mode=ro" % БД, uri=True, timeout=60)
всего = c.execute("SELECT COUNT(*) FROM obzvon").fetchone()[0]
пусто = c.execute("SELECT COUNT(*) FROM obzvon "
                  " WHERE revenue_rub IS NULL "
                  "    OR CAST(revenue_rub AS REAL) <= 0").fetchone()[0]
print("строк в базе обзвона: %d" % всего)
print("без выручки (0/пусто):%d (%.1f%%)" % (пусто, 100.0 * пусто / всего))

по_напр = defaultdict(list)
всё = []
for нап, в in c.execute("SELECT division, revenue_rub FROM obzvon "
                        " WHERE revenue_rub IS NOT NULL "
                        "   AND CAST(revenue_rub AS REAL) > 0"):
    try:
        в = float(в)
    except Exception:                                          # noqa: BLE001
        continue
    if в <= 0:
        continue
    всё.append(в)
    по_напр[str(нап or "без направления")].append(в)
c.close()
print("с выручкой:           %d (%.1f%%)" % (len(всё), 100.0 * len(всё) / всего))

печ = lambda в: "{:,.0f}".format(в).replace(",", " ")          # noqa: E731

def свод(имя, ряд):
    ряд = sorted(ряд)
    n = len(ряд)
    рез = ряд[int(n * 0.05):n - int(n * 0.05)] or ряд
    print("%-18s %7d  ср %14s  мед %13s  ср-без-хвостов %13s"
          % (имя, n, печ(statistics.mean(ряд)), печ(statistics.median(ряд)),
             печ(statistics.mean(рез))))

print("")
свод("вся база", всё)
for нап in sorted(по_напр):
    свод(нап, по_напр[нап])

ряд = sorted(всё)
n = len(ряд)
print("")
print("=== перцентили по всей базе ===")
for p in (1, 5, 10, 25, 50, 75, 90, 95, 99, 99.9):
    print("   p%-6s %16s" % (("%g" % p), печ(ряд[min(n - 1, int(n * p / 100.0))])))
print("   макс   %16s" % печ(ряд[-1]))

СТУПЕНИ = [(0, 10e6, "меньше 10 млн"), (10e6, 50e6, "10-50 млн"),
           (50e6, 200e6, "50-200 млн"), (200e6, 1e9, "200 млн - 1 млрд"),
           (1e9, 10e9, "1-10 млрд"), (10e9, 1e15, "больше 10 млрд")]
print("")
print("=== разбивка по размеру ===")
шапка = "%-20s %9s" % ("размер", "вся база")
напры = sorted(по_напр)
for нап in напры:
    шапка += " %12s" % нап[:12]
print(шапка)
for низ, верх, имя in СТУПЕНИ:
    стр = "%-20s %6d %2s" % (имя, sum(1 for в in ряд if низ <= в < верх),
                             "%.0f%%" % (100.0 * sum(1 for в in ряд
                                                     if низ <= в < верх) / n))
    for нап in напры:
        р = по_напр[нап]
        k = sum(1 for в in р if низ <= в < верх)
        стр += " %6d %5s" % (k, "%.0f%%" % (100.0 * k / len(р)))
    print(стр)

print("")
print("=== сколько дотягивает до порога (вся база) ===")
for порог, п in [(10e6, "10 млн"), (50e6, "50 млн"), (100e6, "100 млн"),
                 (200e6, "200 млн"), (500e6, "500 млн"), (1e9, "1 млрд")]:
    k = sum(1 for в in ряд if в >= порог)
    print("   от %-8s %7d (%4.1f%%)" % (п, k, 100.0 * k / n))
