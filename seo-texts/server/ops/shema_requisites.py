# -*- coding: utf-8 -*-
"""Схема requisites и что в ней уже лежит — перед заливкой."""
import sqlite3

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
print("=== СХЕМА requisites ===")
for r in e.execute("PRAGMA table_info(requisites)"):
    print("   %-3s %-24s %-10s pk=%s" % (r[0], r[1], r[2], r[5]))
print("")
print("=== ИНДЕКСЫ ===")
for r in e.execute("PRAGMA index_list(requisites)"):
    print("   %s уникальный=%s" % (r[1], r[2]))
    for c in e.execute("PRAGMA index_info(%s)" % r[1]):
        print("      поле %s" % c[2])
print("")
ддл = e.execute("SELECT sql FROM sqlite_master WHERE name='requisites'").fetchone()
print("=== DDL ===")
print(ддл[0] if ддл else "нет")
print("")
n = e.execute("SELECT COUNT(*) FROM requisites").fetchone()[0]
print("строк: %d" % n)
print("")
print("=== ТРИ ОБРАЗЦА ===")
e.row_factory = sqlite3.Row
for r in e.execute("SELECT * FROM requisites LIMIT 3"):
    d = {k: (str(r[k])[:30] if r[k] is not None else None) for k in r.keys()}
    print("   %s" % d)
e.close()
