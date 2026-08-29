# -*- coding: utf-8 -*-
"""Режим журналирования баз: WAL или нет. От этого зависит, блокируют ли
читатели писателя."""
import sqlite3
for п in (r"C:\sender\enrich.db", r"C:\sender\sender.db",
          r"C:\sender\obzvon-index.db"):
    try:
        c = sqlite3.connect("file:%s?mode=ro" % п, uri=True, timeout=10)
        режим = c.execute("PRAGMA journal_mode").fetchone()[0]
        размер = c.execute("PRAGMA page_size").fetchone()[0]
        c.close()
        print("%-28s журнал=%-8s страница=%d" % (п.split("\\")[-1], режим, размер))
    except Exception as ex:
        print("%-28s %s" % (п.split("\\")[-1], str(ex)[:60]))
import os, time
for п in (r"C:\sender\enrich.db-wal", r"C:\sender\enrich.db-journal"):
    if os.path.exists(п):
        print("   есть %s (%.1f МБ, изменён %s)"
              % (os.path.basename(п), os.path.getsize(п) / 1048576,
                 time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
