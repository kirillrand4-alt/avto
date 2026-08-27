# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True, timeout=60)
print("тип колонки:", [r[2] for r in c.execute("PRAGMA table_info(obzvon)") if r[1] == "revenue_rub"])
print("typeof():", [dict(zip(("t", "n"), r)) for r in c.execute(
    "SELECT typeof(revenue_rub) t, COUNT(*) n FROM obzvon GROUP BY 1")])
print("образцы:", [r[0] for r in c.execute(
    "SELECT DISTINCT revenue_rub FROM obzvon LIMIT 8")])
print("CAST=0:", c.execute("SELECT COUNT(*) FROM obzvon "
                           " WHERE CAST(revenue_rub AS REAL) <= 0").fetchone()[0])
print("NULL/пусто:", c.execute("SELECT COUNT(*) FROM obzvon "
                               " WHERE revenue_rub IS NULL OR TRIM(COALESCE(revenue_rub,''))=''").fetchone()[0])
c.close()
