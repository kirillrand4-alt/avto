# -*- coding: utf-8 -*-
"""Сырые строки лидов #79/#77/#25 целиком — откуда взялась метка."""
import io
import re
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for н in (79, 77, 74, 25):
    р = c.execute("SELECT * FROM leads WHERE id=?", (н,)).fetchone()
    if not р:
        continue
    print("=== ЛИД #%d ===" % н)
    for к in р.keys():
        з = р[к]
        if з not in (None, ""):
            print("  %-18s %s" % (к, str(з).replace("\n", " ")[:150]))
    print()

print("=== ЕСТЬ ЛИ ПЕРЕВОД МЕТОК В БОЕВОМ store.create_lead ===")
т = io.open(r"C:\sender\sender\store.py", encoding="utf-8").read()
и = т.find("def create_lead")
print(т[и:и + 2000] if и >= 0 else "create_lead не найден")
