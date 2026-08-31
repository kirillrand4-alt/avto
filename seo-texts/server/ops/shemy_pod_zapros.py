# -*- coding: utf-8 -*-
"""Схемы под запрос: направление, выручка, источник почты, кому писали."""
import sqlite3

for имя, путь in (("enrich.db", r"C:\sender\enrich.db"),
                  ("sender.db", r"C:\sender\sender.db")):
    c = sqlite3.connect("file:%s?mode=ro" % путь, uri=True, timeout=60)
    print("\n########## %s ##########" % имя)
    таблицы = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("таблицы: %s" % ", ".join(таблицы))
    интерес = ("companies", "emails", "requisites", "sites", "stage_log",
               "recipients", "campaigns", "segments", "suppression",
               "ai_letter_log", "confirm_reviews", "messages")
    for т in таблицы:
        if т not in интерес:
            continue
        столбцы = [(r[1], r[2]) for r in c.execute("PRAGMA table_info(%s)" % т)]
        n = c.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        print("\n-- %s (%d строк)" % (т, n))
        print("   %s" % ", ".join("%s:%s" % (a, b) for a, b in столбцы))
    c.close()
