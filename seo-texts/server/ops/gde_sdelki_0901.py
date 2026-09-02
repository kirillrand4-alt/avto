# -*- coding: utf-8 -*-
"""Только чтение: где в базе данные о компаниях, с которыми есть сделка."""
import sqlite3

for имя, путь in (("sender", r"C:\sender\sender.db"), ("enrich", r"C:\sender\enrich.db")):
    c = sqlite3.connect("file:%s?mode=ro" % путь.replace("\\", "/"), uri=True)
    c.row_factory = sqlite3.Row
    т = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    инт = [x for x in т if any(k in x.lower() for k in
           ("lead", "deal", "sdelk", "client", "klient", "bitrix", "crm", "company",
            "companies", "obzvon"))]
    print("=== %s: интересные таблицы ===" % имя)
    for tn in инт:
        try:
            n = c.execute("SELECT COUNT(*) FROM %s" % tn).fetchone()[0]
            кол = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % tn)]
            print("  %-18s %6d строк | %s" % (tn, n, ", ".join(кол)[:110]))
        except Exception as ex:
            print("  %-18s %s" % (tn, str(ex)[:60]))

print("\n=== leads: что внутри ===")
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
try:
    кол = [r["name"] for r in s.execute("PRAGMA table_info(leads)")]
    print("  колонки: %s" % ", ".join(кол))
    for р in s.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 3"):
        print("  %s" % {k: str(р[k])[:44] for k in кол[:9]})
except Exception as ex:
    print("  ", str(ex)[:80])

print("\n=== ИТОГ: есть ли база обзвона с компаниями ===")
import os
for п in (r"C:\sender\obzvon-index.db", r"C:\sender\seo.db"):
    print("  %s: %s" % (п, "есть, %d МБ" % (os.path.getsize(п) // 1048576)
                        if os.path.exists(п) else "нет"))
