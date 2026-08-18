# -*- coding: utf-8 -*-
"""Есть ли в обогащении таблица паспортов сайта и что в ней лежит."""
import os
import sqlite3

ENRICH = r"C:\sender\enrich.db"
con = sqlite3.connect(f"file:{ENRICH}?mode=ro", uri=True, timeout=10)
таблицы = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("таблиц в enrich.db:", len(таблицы))
print([t for t in таблицы if "site" in t or "sait" in t or "sayt" in t])
for т in ("site_facts", "sites", "site_text"):
    if т in таблицы:
        n = con.execute(f"SELECT COUNT(*) FROM {т}").fetchone()[0]
        колонки = [r[1] for r in con.execute(f"PRAGMA table_info({т})")]
        print(f"\n{т}: строк {n}, колонки {колонки}")
        for r in con.execute(f"SELECT * FROM {т} LIMIT 2"):
            print("  " + str(r)[:300])
print("\nвсе таблицы:", таблицы)
# где вообще лежат url компаний
for т in таблицы:
    к = [r[1] for r in con.execute(f"PRAGMA table_info({т})")]
    if any(x in ("url", "site", "website", "domain") for x in к):
        n = con.execute(f"SELECT COUNT(*) FROM {т}").fetchone()[0]
        print(f"  {т}: {n} строк, колонки {к[:12]}")
con.close()
