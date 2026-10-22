# -*- coding: utf-8 -*-
"""Карточка confirm целиком (все поля; длинные — 700 знаков). kartochka_vsya.py <id,id>"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for i in sys.argv[1].split(","):
    r = c.execute("SELECT * FROM confirm_reviews WHERE id=?", (int(i),)).fetchone()
    print("=====", i)
    for k in r.keys():
        if r[k] not in (None, ""):
            print("  %-16s %s" % (k, str(r[k])[:700]))
