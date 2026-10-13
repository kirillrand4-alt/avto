# -*- coding: utf-8 -*-
"""Разбор вердиктов «не мейер»/«не покупатель» в базе «наш или нет»: откуда, по
какому сайту, нет ли противоречий. Только чтение.

    razbor_ne_meyer.py "Зерноград" "Щигров" ...
"""
import sqlite3
import sys
from collections import Counter
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
e.row_factory = sqlite3.Row
кол = [r[1] for r in e.execute("PRAGMA table_info(companies)")]
print("колонки companies:", ", ".join(кол))
таблицы = [r[0] for r in e.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("таблицы enrich:", ", ".join(таблицы))
св = Counter()
for р in e.execute("SELECT verdikt_napr, verdikt_rusprom, verdikt_istochnik, count(*) n FROM companies "
                   "WHERE verdikt_napr IS NOT NULL OR verdikt_rusprom IS NOT NULL GROUP BY 1,2,3"):
    print("  %s / %s / %s: %d" % tuple(р))
for назв in sys.argv[1:]:
    for р in e.execute("SELECT * FROM companies WHERE name LIKE ? LIMIT 3", ("%" + назв + "%",)):
        д = dict(р)
        print("--- %s | %s" % (д.get("inn"), д.get("name")))
        for k, v in д.items():
            if v not in (None, "") and k not in ("name", "inn") and len(str(v)) < 400:
                print("    %s: %s" % (k, str(v)[:200]))
print("=== РАЗБОР НЕ МЕЙЕР ===")
