# -*- coding: utf-8 -*-
"""Лид целиком: lid_tekst.py <id>. Только чтение."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM leads WHERE id=?", (int(sys.argv[1]),)).fetchone()
for k in r.keys():
    print("%s: %s" % (k, r[k]))
