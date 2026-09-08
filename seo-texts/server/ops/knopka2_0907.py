# -*- coding: utf-8 -*-
"""Только чтение: с какого ящика и на какой адрес уходит ответ из ленты."""
import io
import os
import re

for корень in (r"C:\sender\server", r"C:\sender\web", r"C:\sender\sender"):
    if not os.path.isdir(корень):
        continue
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "node_modules", "tests")]
        for ф in фф:
            if not ф.endswith(".py") or ф == "store.py":
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            if "otvet_kak_pismo" not in т:
                continue
            for м in re.finditer(r"otvet_kak_pismo", т):
                нач = max(т.rfind("\ndef ", 0, м.start()),
                          т.rfind("\n    def ", 0, м.start()),
                          т.rfind("\n@", 0, м.start()))
                нач = нач if нач > 0 else max(0, м.start() - 2600)
                print("=" * 14 + " %s " % п.replace(r"C:\sender", "") + "=" * 14)
                print(т[нач:м.start() + 400])
                break
