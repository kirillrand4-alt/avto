# -*- coding: utf-8 -*-
"""Строка подмены источника в enrich_db и кто добирает почты из кэша."""
import io
import os
import re

# 1) подмена в enrich_db
П = r"C:\sender\server\enrich_db.py"
т = io.open(П, encoding="utf-8", errors="replace").read()
стр = т.splitlines()
for i, с in enumerate(стр):
    if "'own-site'" in с and "source" in с:
        а, б = max(0, i - 16), min(len(стр), i + 8)
        print("=== enrich_db.py, строки %d-%d ===" % (а + 1, б))
        for j in range(а, б):
            print("%5d| %s" % (j + 1, стр[j][:150]))
        break

# 2) кто пишет pometka='кэш-добор' для ПОЧТ (не ФИО)
print("")
print("=== КТО ДОБИРАЕТ ПОЧТЫ ИЗ КЭША ===")
for корень in (r"C:\sender\server", r"C:\sender\server\ops"):
    if not os.path.isdir(корень):
        continue
    for имя in sorted(os.listdir(корень)):
        if not имя.endswith(".py"):
            continue
        ф = os.path.join(корень, имя)
        try:
            т2 = io.open(ф, encoding="utf-8", errors="replace").read()
        except Exception:                                      # noqa: BLE001
            continue
        if "кэш-добор" not in т2:
            continue
        м = re.search(r'"""(.{0,700}?)"""', т2, re.S)
        print("")
        print("--- %s ---" % имя)
        if м:
            print("   " + " ".join(м.group(1).split())[:520])
        for м2 in re.finditer(r"^.{0,110}кэш-добор.{0,110}$", т2, re.M):
            с = м2.group(0).strip()
            if с and not с.lstrip().startswith("#"):
                print("      " + с[:140])
        # откуда берёт страницы
        for м3 in re.finditer(r"^.{0,90}(pagecache|PAGECACHE|КЭШ|kesh)"
                              r".{0,90}$", т2, re.M):
            print("      путь: " + м3.group(0).strip()[:130])
