# -*- coding: utf-8 -*-
"""Поиск человека/телефона/адреса по enrich.db и obzvon-index.db во всех текстовых колонках:
poisk_cheloveka.py ПОДСТРОКА [...]. Только чтение."""
import sqlite3, sys
for путь in (r"C:\sender\enrich.db", r"C:\sender\obzvon-index.db"):
    c = sqlite3.connect(путь, timeout=90)
    for (т,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        кол = [x[1] for x in c.execute("PRAGMA table_info(%s)" % т) if (x[2] or "").upper() in ("TEXT", "")]
        if not кол: continue
        for п in sys.argv[1:]:
            где = " OR ".join("%s LIKE ?" % k for k in кол)
            try:
                for r in c.execute("SELECT * FROM %s WHERE %s LIMIT 5" % (т, где), ["%" + п + "%"] * len(кол)):
                    print("%s.%s [%s]: %s" % (путь.split("\\")[-1], т, п, str(tuple(str(x)[:80] for x in r))[:600]))
            except Exception as ex:  # noqa: BLE001
                pass
