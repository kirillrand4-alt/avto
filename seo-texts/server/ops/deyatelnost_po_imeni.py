# -*- coding: utf-8 -*-
"""Деятельность компаний из enrich.companies по подстроке названия: deyatelnost_po_imeni.py ПОДСТРОКА [...]"""
import sqlite3, sys
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
for п in sys.argv[1:]:
    for r in e.execute("SELECT name, okved, substr(COALESCE(activity,''),1,250) FROM companies WHERE name LIKE ? LIMIT 2", ("%" + п + "%",)):
        print(r)
