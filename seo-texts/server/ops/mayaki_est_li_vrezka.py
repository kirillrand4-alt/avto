# -*- coding: utf-8 -*-
"""Есть ли на СЕРВЕРЕ код, который подмешивает маяк в партию и смотрит папку."""
import io
import os
имена = ("mayaki", "gde_pismo", "КАМПАНИЯ", "mayak")
for корень in (r"C:\sender\sender",):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "web", "tests")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            т = io.open(п, encoding="utf-8", errors="ignore").read()
            for i, стр in enumerate(т.split("\n")):
                if "mayaki" in стр or "gde_pismo" in стр or '"mayak"' in стр \
                        or "'mayak'" in стр:
                    print("%s:%d| %s" % (os.path.basename(п), i + 1,
                                         стр.strip()[:120]))
