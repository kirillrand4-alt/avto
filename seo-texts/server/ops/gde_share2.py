# -*- coding: utf-8 -*-
import io, os
НАЙТИ = "ответ компании"
for корень in (r"C:\sender\sender", r"C:\sender\server"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("node_modules", "__pycache__",
                                              ".git", "venv", ".venv", "logs")]
        for имя in файлы:
            if not имя.endswith((".py", ".tsx", ".ts", ".html", ".js")):
                continue
            п = os.path.join(путь, имя)
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            if НАЙТИ in т:
                стр = т.split("\n")
                print("=== %s ===" % п)
                for i, s in enumerate(стр):
                    if НАЙТИ in s:
                        for j in range(max(0, i - 8), min(len(стр), i + 9)):
                            print("%5d| %s" % (j + 1, стр[j][:150]))
                        print("  ...")
