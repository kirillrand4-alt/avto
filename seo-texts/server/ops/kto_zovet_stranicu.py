# -*- coding: utf-8 -*-
import io, os
for корень in (r"C:\sender\sender",):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("node_modules", "__pycache__",
                                              "web", "tests")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            s = io.open(п, encoding="utf-8", errors="ignore").read()
            if "lid_stranica" in s or "sobrat(" in s:
                стр = s.split("\n")
                for i, ln in enumerate(стр):
                    if "lid_stranica" in ln or "sobrat(" in ln:
                        print("=== %s:%d ===" % (п, i + 1))
                        for j in range(max(0, i - 30), min(len(стр), i + 12)):
                            print("%5d| %s" % (j + 1, стр[j][:150]))
                        print()
