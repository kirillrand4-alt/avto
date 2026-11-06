# -*- coding: utf-8 -*-
"""Схема obzvon-index.db и enrich.db (таблицы/колонки, где есть имя/должность контакта)."""
import sqlite3
for б in (r"C:\sender\obzvon-index.db", r"C:\sender\enrich.db"):
    c = sqlite3.connect("file:%s?mode=ro" % б, uri=True, timeout=30)
    print("==", б)
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)]
        n = c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
        print("  %s (%d): %s" % (t, n, ", ".join(cols)[:300]))
