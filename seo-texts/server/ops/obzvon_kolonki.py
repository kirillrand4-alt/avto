# -*- coding: utf-8 -*-
"""Колонки таблицы obzvon (obzvon-index.db). Только чтение."""
import sqlite3
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
print([x[1] for x in o.execute("PRAGMA table_info(obzvon)")])
