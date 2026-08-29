# -*- coding: utf-8 -*-
import sqlite3
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
e.row_factory = sqlite3.Row
print("таблицы:")
for r in e.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"):
    try:
        n = e.execute("SELECT COUNT(*) FROM %s" % r["name"]).fetchone()[0]
    except Exception:
        n = "?"
    print("   %-26s %s" % (r["name"], n))
for т in ("companies", "obzvon"):
    try:
        кол = [r["name"] for r in e.execute("PRAGMA table_info(%s)" % т)]
        print("\n%s: %s" % (т, ", ".join(кол[:22])))
    except Exception as ex:
        print("\n%s: %s" % (т, ex))
e.close()
o = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True,
                    timeout=60)
o.row_factory = sqlite3.Row
print("\n--- обзвон ---")
for r in o.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"):
    try:
        n = o.execute("SELECT COUNT(*) FROM %s" % r["name"]).fetchone()[0]
    except Exception:
        n = "?"
    print("   %-26s %s" % (r["name"], n))
o.close()
