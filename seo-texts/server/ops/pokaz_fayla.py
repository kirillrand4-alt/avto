# -*- coding: utf-8 -*-
"""Строки файла кода панели: pokaz_fayla.py ФАЙЛ ОТ ДО (файл относительно C:\\sender\\sender)"""
import io, os, sys
т = io.open(os.path.join(r"C:\sender\sender", sys.argv[1]), encoding="utf-8").read().splitlines()
for j in range(int(sys.argv[2]) - 1, min(len(т), int(sys.argv[3]))):
    print("%5d|%s" % (j + 1, т[j]))
