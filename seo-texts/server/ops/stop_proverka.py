# -*- coding: utf-8 -*-
"""Есть ли значение в стоп-листе: stop_proverka.py <значение>. Только чтение."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
print(c.execute("SELECT scope, value, reason, source, created_at FROM suppression WHERE lower(value)=?", (sys.argv[1].lower(),)).fetchall())
