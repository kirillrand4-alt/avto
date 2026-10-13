# -*- coding: utf-8 -*-
"""Откуда взяты адреса (enrich.emails: source, source_url, role, imya_ok, progon)."""
import sqlite3
import sys
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
cx.row_factory = sqlite3.Row
for а in sys.argv[1].split(","):
    for р in cx.execute("SELECT inn, email, source, source_url, role, progon, rol_istochnik FROM emails WHERE lower(email)=?", (а.lower(),)):
        print("   %s | ист=%s | url=%s | роль=%s | прогон=%s | %s" % (р["email"], р["source"], str(р["source_url"])[:70],
              р["role"], р["progon"], р["rol_istochnik"]))
print("=== ИСТОЧНИК АДРЕСОВ ===")
