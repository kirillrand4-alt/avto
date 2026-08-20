# -*- coding: utf-8 -*-
"""Есть ли у пищевых компаний контакты по ролям: качество, технолог, инженер.

Владелец: «желательно отправлять специалистам по кач-ву, технологам,
инженерам, ЛПР». Смотрим, чем мы вообще располагаем: только директор из
реестра или есть люди с должностями из обогащения.
"""
import sqlite3
from collections import Counter

for путь in (r"C:\sender\enrich.db", r"C:\sender\obzvon-index.db"):
    c = sqlite3.connect("file:%s?mode=ro" % путь.replace("\\", "/"), uri=True)
    print(f"== {путь} ==")
    for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        try:
            n = c.execute(f"SELECT COUNT(*) FROM [{r['name'] if 0 else r[0]}]"
                          ).fetchone()[0]
        except Exception:                                        # noqa: BLE001
            n = "?"
        print(f"   {r[0]:<24} {n}")
    c.close()

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db".replace("\\", "/"),
                    uri=True)
имена = [r[0] for r in e.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
for т in имена:
    кол = [x[1] for x in e.execute(f"PRAGMA table_info([{т}])")]
    if any("dolzh" in k or "должн" in k or "role" in k or "post" in k
           for k in кол):
        print(f"\nтаблица с должностями: {т} -> {кол}")
        for r in e.execute(f"SELECT * FROM [{т}] LIMIT 3"):
            print("   ", dict(zip(кол, r)))
