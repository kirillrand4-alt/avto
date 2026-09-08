# -*- coding: utf-8 -*-
"""Только чтение: кто вызывает create_lead, кроме store.py."""
import io
import os
import re

цели = []
for корень in (r"C:\sender\sender", r"C:\sender\server", r"C:\sender\web"):
    if not os.path.isdir(корень):
        continue
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "tests", "node_modules")]
        for ф in фф:
            if ф.endswith(".py") and "test" not in ф and ф != "store.py":
                п = os.path.join(путь, ф)
                т = io.open(п, encoding="utf-8", errors="ignore").read()
                if "create_lead" in т:
                    цели.append((п, т))

for п, т in цели:
    for м in re.finditer(r"create_lead", т):
        начало = т.rfind("\n    def ", 0, м.start())
        начало = начало if начало > 0 else max(0, м.start() - 1500)
        print("\n" + "=" * 16 + " %s " % п.replace(r"C:\sender", "") + "=" * 16)
        print(т[начало:м.start() + 1400])
        break

print("\n=== ФАЙЛЫ-ВЫЗЫВАТЕЛИ ===")
for п, _ in цели:
    print("  " + п.replace(r"C:\sender", ""))
