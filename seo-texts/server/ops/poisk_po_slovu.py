# -*- coding: utf-8 -*-
"""Поиск компании по куску слова в названии/сайте/почтах: enrich, обзвон, получатели."""
import sqlite3
import sys
слова = [с.lower() for с in sys.argv[1:]]
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
for с in слова:
    for р in cx.execute("SELECT inn, name, site, region FROM companies WHERE lower(name) LIKE ? OR lower(site) LIKE ? OR lower(short_name) LIKE ? LIMIT 8",
                        ("%" + с + "%",) * 3):
        print("enrich [%s]: %s" % (с, р))
    for р in cx.execute("SELECT inn, email FROM emails WHERE lower(email) LIKE ? LIMIT 5", ("%" + с + "%",)):
        print("enrich почта [%s]: %s" % (с, р))
ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=30)
for с in слова:
    for р in ox.execute("SELECT inn, name_short, region, sites, emails_base FROM obzvon WHERE lower(name_short) LIKE ? OR lower(name_full) LIKE ? "
                        "OR lower(sites) LIKE ? OR lower(emails_base) LIKE ? LIMIT 8", ("%" + с + "%",) * 4):
        print("обзвон [%s]: %s" % (с, tuple(str(x)[:60] for x in р)))
print("=== ПОИСК ПО СЛОВУ ===")
