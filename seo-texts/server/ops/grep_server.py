# -*- coding: utf-8 -*-
"""Поиск строки в файлах кода панели на сервере: grep_server.py ПОДСТРОКА [файл…] (по умолчанию sender/*.py), ±3 строки."""
import glob, io, os, sys
к = sys.argv[1]
файлы = [os.path.join(r"C:\sender\sender", f) for f in sys.argv[2:]] or glob.glob(r"C:\sender\sender\*.py")
for п in файлы:
    т = io.open(п, encoding="utf-8").read().splitlines()
    for i, s in enumerate(т):
        if к in s:
            print("---- %s:%d" % (os.path.basename(п), i + 1))
            for j in range(max(0, i - 3), min(len(т), i + 4)):
                print("%5d|%s" % (j + 1, т[j]))
