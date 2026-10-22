# -*- coding: utf-8 -*-
"""Настройки панели (panel_settings) — ключи и значения, коротко. Только чтение.
    panel_nastroyki.py [фильтр_ключа]"""
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
ф = sys.argv[1].lower() if len(sys.argv) > 1 else ""
for k, v in c.execute("SELECT key, value FROM panel_settings ORDER BY key"):
    if ф in str(k).lower():
        print("%-40s %s" % (k, str(v)[:600]))
