# -*- coding: utf-8 -*-
"""Сайт у служебных ИНН в enrich.companies (сверка нумерации книг)."""
import sqlite3
import sys
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
for inn in sys.argv[1].split(","):
    р = cx.execute("SELECT inn, site, name FROM companies WHERE inn=?", (inn,)).fetchone()
    print("   %s -> %s" % (inn, р))
print("служебных всего: %s, максимум %s" % cx.execute(
    "SELECT count(*), max(inn) FROM companies WHERE inn LIKE '00%' AND length(inn)=11").fetchone())
print("=== СЛУЖЕБНЫЕ ===")
