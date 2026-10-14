# -*- coding: utf-8 -*-
"""Колонки enrich.emails и sender.addr_probe (для отбора адреса)."""
import sqlite3
e = sqlite3.connect(r"C:\sender\enrich.db")
print("emails:", [r[1] for r in e.execute("PRAGMA table_info(emails)")])
print(e.execute("SELECT * FROM emails LIMIT 2").fetchall())
c = sqlite3.connect(r"C:\sender\sender.db")
print("addr_probe:", [r[1] for r in c.execute("PRAGMA table_info(addr_probe)")])
print(c.execute("SELECT verdict, count(*) FROM addr_probe GROUP BY 1").fetchall())
print("=== КОЛОНКИ ===")
