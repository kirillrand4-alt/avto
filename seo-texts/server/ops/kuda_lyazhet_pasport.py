# -*- coding: utf-8 -*-
"""Куда физически кладётся «обогащение»: схема enrich.db и ключи."""
import sqlite3

cx = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True)
cx.row_factory = sqlite3.Row
for т in ("companies", "emails", "signals"):
    try:
        схема = cx.execute("SELECT sql FROM sqlite_master WHERE name=?",
                           (т,)).fetchone()
    except Exception as ex:                                     # noqa: BLE001
        print("%s: %s" % (т, str(ex)[:60]))
        continue
    if not схема:
        print("таблицы %s нет" % т)
        continue
    n = cx.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
    print("")
    print("=== %s: %d строк ===" % (т, n))
    print(str(схема["sql"])[:600])

print("")
print("--- бывают ли нечисловые ключи в companies.inn ---")
n = cx.execute("SELECT COUNT(*) FROM companies "
               " WHERE inn GLOB '*[^0-9]*'").fetchone()[0]
print("   нечисловых inn: %d" % n)
for р in cx.execute("SELECT inn, name FROM companies "
                    " WHERE inn GLOB '*[^0-9]*' LIMIT 5"):
    print("      %s | %s" % (р["inn"], str(р["name"])[:50]))
print("")
print("--- длины inn ---")
for р in cx.execute("SELECT length(inn) L, COUNT(*) n FROM companies "
                    " GROUP BY 1 ORDER BY 2 DESC LIMIT 6"):
    print("   длина %-3s %7d" % (р["L"], р["n"]))
cx.close()
print("")
print("=" * 74)
print("=== КУДА ЛЯЖЕТ ПАСПОРТ ===")
