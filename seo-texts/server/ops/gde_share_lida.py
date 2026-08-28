# -*- coding: utf-8 -*-
"""Где на сервере живёт публичная страница лида (ссылка для продажников)."""
import io
import os
ИСКАТЬ = ("ответ компании", "письмо не дошло", "share", "публичн")
КОРНИ = [r"C:\sender\sender", r"C:\sender\server", r"C:\sender"]
видел = set()
for корень in КОРНИ:
    for путь, каталоги, файлы in os.walk(корень):
        каталоги[:] = [d for d in каталоги
                       if d not in ("node_modules", "dist", "__pycache__",
                                    ".git", "venv", ".venv", "logs")]
        for имя in файлы:
            if not имя.endswith((".py", ".tsx", ".ts", ".html", ".jinja", ".j2")):
                continue
            п = os.path.join(путь, имя)
            if п in видел:
                continue
            видел.add(п)
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            for сл in ИСКАТЬ:
                if сл in т:
                    строки = [i + 1 for i, s in enumerate(т.split("\n")) if сл in s]
                    print("%s :: %r строки %s" % (п, сл, строки[:8]))
print("просмотрено файлов: %d" % len(видел))
