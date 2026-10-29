# -*- coding: utf-8 -*-
"""Все следы одного ИНН в enrich.db: каждая таблица, где есть колонка inn,
плюс строки, где упомянут указанный домен. Только чтение.
Аргументы: ИНН [домен]"""
import sqlite3
import sys

инн = sys.argv[1]
домен = sys.argv[2] if len(sys.argv) > 2 else None
for путь in [п for п in (r"C:\sender\enrich.db", r"C:\sender\sender.db") if len(sys.argv) < 4 or sys.argv[3] in п]:
    к = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
    к.row_factory = sqlite3.Row
    print("#" * 20, путь)
    for (т,) in к.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        кол = [r[1] for r in к.execute('PRAGMA table_info("%s")' % т)]
        if "inn" not in кол:
            continue
        стр = к.execute('SELECT * FROM "%s" WHERE inn=? LIMIT 20' % т, (инн,)).fetchall()
        for с in стр:
            print("== %s: %s" % (т, {k: (str(с[k])[:160] if с[k] is not None else None)
                                     for k in с.keys() if с[k] not in (None, "")}))
    if домен:
        for (т,) in к.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            кол = [r[1] for r in к.execute('PRAGMA table_info("%s")' % т)]
            for кл in кол:
                if кл in ("site", "domain", "url", "website", "sayt", "email"):
                    try:
                        for с in к.execute('SELECT * FROM "%s" WHERE "%s" LIKE ? LIMIT 5' % (т, кл), ("%" + домен + "%",)):
                            print("~~ %s.%s: %s" % (т, кл, {k: str(с[k])[:200] for k in с.keys() if с[k] not in (None, "")}))
                    except Exception as e:
                        print("err", т, кл, e)
