# -*- coding: utf-8 -*-
"""Только чтение: маршрут API, принимающий ответ оператора."""
import io
import os
import re

for корень in (r"C:\sender\server", r"C:\sender\sender"):
    for путь, пп, фф in os.walk(корень):
        пп[:] = [п for п in пп if п not in ("__pycache__", "ops", ".git",
                                            "node_modules", "tests")]
        for ф in фф:
            if not ф.endswith(".py"):
                continue
            п = os.path.join(путь, ф)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            for м in re.finditer(r'@\w+\.(post|put)\(\s*["\'][^"\']*'
                                 r'(reply|otvet)[^"\']*["\']', т, re.I):
                конец = т.find("\n@", м.end())
                конец = конец if конец > 0 else м.end() + 3000
                print("\n" + "=" * 12 + " %s " % п.replace(r"C:\sender", "")
                      + "=" * 12)
                print(т[м.start():min(конец, м.start() + 3000)])
