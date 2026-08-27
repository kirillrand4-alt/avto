# -*- coding: utf-8 -*-
import sqlite3
for бд, табл in ((r"C:\sender\obzvon-index.db", "obzvon"),
                 (r"C:\sender\enrich.db", "companies")):
    c = sqlite3.connect("file:%s?mode=ro" % бд, uri=True, timeout=30)
    print("%s.%s:" % (бд, табл))
    print("   " + ", ".join(r[1] for r in c.execute("PRAGMA table_info(%s)" % табл)))
    c.close()
