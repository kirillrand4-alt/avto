# -*- coding: utf-8 -*-
"""Только чтение: бэкенд ответа из ленты — какой ящик и какой адрес."""
import io
import os
import re

КЛЮЧИ = ("adres_iz_pisma", "adres_dal", "bez_privyazki")
for корень in (r"C:\sender\server", r"C:\sender\sender"):
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "node_modules", "tests")]
        for ф in фф:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            if not any(к in т for к in КЛЮЧИ):
                continue
            print("=== %s ===" % п.replace(r"C:\sender", ""))
            for к in КЛЮЧИ:
                for м in re.finditer(re.escape(к), т):
                    нач = max(т.rfind("\ndef ", 0, м.start()),
                              т.rfind("\n    def ", 0, м.start()))
                    нач = нач if нач > 0 else max(0, м.start() - 1500)
                    print(т[нач:м.start() + 1500])
                    break
                break
