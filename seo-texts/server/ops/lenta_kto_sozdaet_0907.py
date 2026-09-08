# -*- coding: utf-8 -*-
"""Только чтение: боевой код, создающий лид из ответа (без тестов)."""
import io
import os
import re

цели = []
for корень in (r"C:\sender\sender", r"C:\sender\server"):
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "tests")]
        for ф in фф:
            if ф.endswith(".py") and "test" not in ф:
                п = os.path.join(путь, ф)
                т = io.open(п, encoding="utf-8", errors="ignore").read()
                if "create_lead(" in т:
                    цели.append((п, т))

print("=== ФАЙЛЫ С create_lead (боевые) ===")
for п, _ in цели:
    print("  " + п.replace(r"C:\sender", ""))

for п, т in цели:
    for м in re.finditer(r"create_lead\(", т):
        начало = т.rfind("\ndef ", 0, м.start())
        начало = начало if начало > 0 else max(0, м.start() - 1800)
        print("\n" + "=" * 18 + " %s " % п.replace(r"C:\sender", "") + "=" * 18)
        print(т[начало:м.start() + 1100])
