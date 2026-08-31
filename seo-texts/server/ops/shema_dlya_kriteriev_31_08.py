# -*- coding: utf-8 -*-
"""Только чтение: схема enrich.db и sender.db под три критерия владельца."""
import json
import sqlite3

for имя, путь in (("enrich", r"C:\sender\enrich.db"), ("sender", r"C:\sender\sender.db")):
    try:
        c = sqlite3.connect("file:%s?mode=ro" % путь.replace("\\", "/"), uri=True)
        c.row_factory = sqlite3.Row
    except Exception as e:
        print("%s: не открылась: %s" % (имя, e))
        continue
    print("\n===== %s (%s) =====" % (имя, путь))
    т = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("  таблиц: %d -> %s" % (len(т), ", ".join(т)))
    инт = [x for x in т if any(k in x.lower() for k in
           ("site", "fact", "recipient", "company", "contact", "revenue",
            "vyruch", "finans", "okved", "email", "pochta"))]
    for tn in инт[:12]:
        try:
            кол = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % tn)]
            n = c.execute("SELECT COUNT(*) FROM %s" % tn).fetchone()[0]
            print("\n  -- %s (%d строк)" % (tn, n))
            print("     колонки: %s" % ", ".join(кол))
            р = c.execute("SELECT * FROM %s LIMIT 1" % tn).fetchone()
            if р:
                for k in кол[:14]:
                    v = str(р[k])
                    print("       %-22s %s" % (k, (v[:90] + "…") if len(v) > 90 else v))
        except Exception as e:
            print("     ошибка: %s" % str(e)[:80])

print("\n=== ИТОГ: что нашлось ===")
print("  (выше перечислены таблицы, где может лежать паспорт, почта и выручка)")
