# -*- coding: utf-8 -*-
"""Только чтение: где лежит выручка. Сканирую ВСЕ таблицы обеих баз."""
import json
import sqlite3

КЛЮЧИ = ("vyruch", "выруч", "revenue", "oborot", "оборот", "finans", "финанс",
         "income", "prib", "приб")
for имя, путь in (("enrich", r"C:\sender\enrich.db"), ("sender", r"C:\sender\sender.db")):
    c = sqlite3.connect("file:%s?mode=ro" % путь.replace("\\", "/"), uri=True)
    c.row_factory = sqlite3.Row
    т = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("\n===== %s: %d таблиц =====" % (имя, len(т)))
    print("  " + ", ".join(т))
    for tn in т:
        try:
            кол = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % tn)]
        except Exception:
            continue
        совп = [k for k in кол if any(x in k.lower() for x in КЛЮЧИ)]
        if совп:
            n = c.execute("SELECT COUNT(*) FROM %s" % tn).fetchone()[0]
            print("  НАЙДЕНО %s (%d строк): %s" % (tn, n, совп))
            for р in c.execute("SELECT %s FROM %s LIMIT 3" % (", ".join(совп), tn)):
                print("     ", dict(р))

# выручка может лежать внутри json-полей
print("\n=== поиск внутри json-полей ===")
c = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for tn, jc in (("company_card", "card_json"), ("companies", "data_json"),
               ("checko", "json"), ("dadata", "json")):
    try:
        р = c.execute("SELECT %s FROM %s LIMIT 1" % (jc, tn)).fetchone()
        if р:
            print("  %s.%s:" % (tn, jc), str(р[0])[:220])
    except Exception as e:
        print("  %s.%s -> нет (%s)" % (tn, jc, str(e)[:50]))

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
р = s.execute("SELECT extra_json FROM recipients WHERE extra_json IS NOT NULL"
              " AND length(extra_json)>50 LIMIT 1").fetchone()
if р:
    try:
        d = json.loads(р["extra_json"])
        print("\n  recipients.extra_json, ключи:", sorted(d.keys())[:40])
        for k in d:
            if any(x in k.lower() for x in КЛЮЧИ):
                print("    ВЫРУЧКА В extra:", k, "=", str(d[k])[:80])
    except Exception as e:
        print("  extra_json не разобрался:", str(e)[:60])
print("\n=== ИТОГ ===")
print("  см. строки «НАЙДЕНО» выше")
