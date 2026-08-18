# -*- coding: utf-8 -*-
"""Пересобрать тексты сайтов заново (после правки фильтра шума)."""
import sqlite3
con = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
n = con.execute("SELECT COUNT(*) FROM site_text").fetchone()[0]
con.execute("DELETE FROM site_text")
con.commit()
con.close()
print(f"очищено записей: {n} — следующий сбор соберёт заново")
