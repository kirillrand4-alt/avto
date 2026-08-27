# -*- coding: utf-8 -*-
"""Где лежит выручка компаний: смотрим схемы баз."""
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
for к in ("obzvon.index_path", "obzvon.enrich_db", "service.enrich_db"):
    print("   %-24s %s" % (к, cfg.get(к, "(нет)")))

for путь in (str(cfg.get("obzvon.index_path", "") or ""),
             r"C:\sender\obzvon-index.db", r"C:\sender\enrich.db"):
    if not путь or not os.path.exists(путь):
        continue
    print("")
    print("=== %s ===" % путь)
    c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=30)
    таблицы = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("   таблиц: %d — %s" % (len(таблицы), ", ".join(таблицы[:18])))
    for т in таблицы:
        кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
        свои = [к for к in кол if any(s in к.lower() for s in
                                      ("vyruch", "revenue", "выруч", "oborot",
                                       "fin", "pribyl", "dohod"))]
        if свои:
            n = c.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
            print("   %-22s строк %-8d поля: %s" % (т, n, ", ".join(свои)))
    c.close()
