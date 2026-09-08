# -*- coding: utf-8 -*-
"""Только чтение: по какому ключу панель делит переписку на отдельные блоки."""
import io
import os
import re

for корень in (r"C:\sender\sender", r"C:\sender\server"):
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "node_modules", "tests")]
        for ф in фф:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            if "n_out" not in т:
                continue
            for м in re.finditer(r"n_out", т):
                нач = max(т.rfind("\ndef ", 0, м.start()),
                          т.rfind("\n    def ", 0, м.start()))
                нач = нач if нач > 0 else max(0, м.start() - 2000)
                print("=" * 12 + " %s " % п.replace(r"C:\sender", "") + "=" * 12)
                print(т[нач:м.start() + 1200])
                break
            break
