# -*- coding: utf-8 -*-
"""Только чтение: как боевой разбор создаёт лид из ответа."""
import inspect
import io
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                   # noqa: E402

print("=== create_lead: полная подпись ===")
print(inspect.signature(Store.create_lead))

print("\n=== ГДЕ ВЫЗЫВАЕТСЯ create_lead ===")
for корень in (r"C:\sender\sender", r"C:\sender\server"):
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git")]
        for ф in фф:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            if "create_lead(" in т:
                for м in re.finditer(r"create_lead\(", т):
                    н = т.rfind("\n", 0, max(0, м.start() - 1400))
                    print("\n--- %s ---" % п.replace(r"C:\sender", ""))
                    print(т[max(0, м.start() - 1400):м.start() + 900])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("\n=== ПОСЛЕДНИЕ ЛИДЫ В ЛЕНТЕ (для образца полей) ===")
for р in c.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 3"):
    print("  " + str({к: v for к, v in dict(р).items() if v not in (None, "")})[:500])
