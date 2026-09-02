# -*- coding: utf-8 -*-
"""Только чтение: что лежит в стоп-листе и есть ли там клиенты со сделками."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
кол = [r["name"] for r in s.execute("PRAGMA table_info(suppression)")]
print("=== suppression: %s ===" % ", ".join(кол))
print("  всего: %d" % s.execute("SELECT COUNT(*) FROM suppression").fetchone()[0])

print("\n=== ПО SCOPE И ПРИЧИНЕ ===")
for р in s.execute("SELECT scope, reason, COUNT(*) n FROM suppression"
                   " GROUP BY scope, reason ORDER BY n DESC LIMIT 20"):
    print("  %-10s %-28s %6d" % (р["scope"], str(р["reason"])[:28], р["n"]))

print("\n=== ПО ИСТОЧНИКУ ===")
for р in s.execute("SELECT source, COUNT(*) n FROM suppression"
                   " GROUP BY source ORDER BY n DESC LIMIT 14"):
    print("  %-34s %6d" % (str(р["source"])[:34], р["n"]))

print("\n=== ПРИМЕРЫ ЗАПИСЕЙ ПО ИНН ===")
for р in s.execute("SELECT * FROM suppression WHERE scope='inn' LIMIT 5"):
    print("  %s" % {k: str(р[k])[:40] for k in кол})

print("\n=== ИТОГ ===")
n_inn = s.execute("SELECT COUNT(*) n FROM suppression WHERE scope='inn'").fetchone()["n"]
print("  записей по ИНН: %d" % n_inn)
print("  (отчёт zaslon-sdelki.json от 13.08 говорил про 3741 ИНН в списке)")
