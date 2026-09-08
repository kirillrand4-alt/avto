# -*- coding: utf-8 -*-
"""Только чтение: форма ответа в ленте и её маршрут."""
import io
import os
import re

цели = []
for корень in (r"C:\sender\web", r"C:\sender\server", r"C:\sender\sender"):
    if not os.path.isdir(корень):
        continue
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "node_modules", "tests")]
        for ф in фф:
            п = os.path.join(путь, ф)
            if os.path.splitext(ф)[1].lower() not in (".html", ".js", ".py",
                                                      ".j2", ".jinja"):
                continue
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if "Ответить на это письмо" in т:
                цели.append((п, т))

print("=== ГДЕ КНОПКА ===")
for п, _ in цели:
    print("  " + п.replace(r"C:\sender", ""))

for п, т in цели[:2]:
    i = т.find("Ответить на это письмо")
    print("\n" + "=" * 12 + " %s " % п.replace(r"C:\sender", "") + "=" * 12)
    print(т[max(0, i - 1800):i + 1800])
