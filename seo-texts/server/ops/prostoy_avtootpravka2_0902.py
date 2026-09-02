# -*- coding: utf-8 -*-
"""Только чтение: где живёт автоотправка и в каком она состоянии."""
import io
import os
import re
import sqlite3

ФАЙЛЫ = []
for корень in (r"C:\sender\sender", r"C:\sender\server", r"C:\sender\web"):
    if not os.path.isdir(корень):
        continue
    for дп, дир, фс in os.walk(корень):
        if "tests" in дп or "node_modules" in дп or "\\ops" in дп:
            continue
        for ф in фс:
            if ф.endswith(".py"):
                ФАЙЛЫ.append(os.path.join(дп, ф))
print("py-файлов просмотрено: %d" % len(ФАЙЛЫ))

нашли = {}
for п in ФАЙЛЫ:
    try:
        т = io.open(п, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    лн = т.splitlines()
    for м in re.finditer(r"(?i)(avtootpravk|автоотправк|autosend|auto_send)", т):
        н = т[:м.start()].count("\n")
        с = лн[н].strip()
        if с.startswith("#") or not с:
            continue
        нашли.setdefault(os.path.relpath(п, r"C:\sender"), []).append((н + 1, с))
for ф, сп in нашли.items():
    print("\n--- %s (%d вхождений) ---" % (ф, len(сп)))
    видел = set()
    for н, с in сп[:14]:
        if с[:50] in видел:
            continue
        видел.add(с[:50])
        print("  %5d| %s" % (н, с[:104]))

print("\n=== НАСТРОЙКИ В БАЗЕ ===")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
таб = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"
                               " AND (name LIKE '%setting%' OR name LIKE '%panel%')")]
print("  таблицы: %s" % таб)
for т2 in таб:
    кол = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % т2)]
    n = c.execute("SELECT COUNT(*) FROM %s" % т2).fetchone()[0]
    print("  %s (%d строк): %s" % (т2, n, ", ".join(кол)))
    for р in c.execute("SELECT * FROM %s LIMIT 30" % т2):
        print("    " + " | ".join("%s=%s" % (k, str(р[k])[:50]) for k in кол)[:150])
