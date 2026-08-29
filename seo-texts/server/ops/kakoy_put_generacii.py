# -*- coding: utf-8 -*-
"""Какой дорогой набираются кандидаты на генерацию и стоит ли там стоп-лист."""
import io
import os
import re

цели = ("candidates(", "_kandidaty_po_gruppe", "_v_stop_liste",
        "query_recipients", "suppressed")
корни = [r"C:\sender\sender", r"C:\sender\_ops", r"C:\sender\server\ops"]
for корень in корни:
    if not os.path.isdir(корень):
        continue
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "web", "tests")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            если = [c for c in цели if c in т]
            if "candidates(" in т or "query_recipients" in т:
                print("%-46s %s" % (os.path.basename(п), ", ".join(если)))
print()
print("=== есть ли правка в выкаченном ai_quota ===")
т = io.open(r"C:\sender\sender\ai_quota.py", encoding="utf-8").read()
print("   _v_stop_liste в файле: %s" % ("да" if "_v_stop_liste" in т else "НЕТ"))
for i, с in enumerate(т.split("\n")):
    if "_v_stop_liste" in с:
        print("   %5d| %s" % (i + 1, с.strip()[:100]))
