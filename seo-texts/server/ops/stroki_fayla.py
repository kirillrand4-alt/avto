# -*- coding: utf-8 -*-
"""Строки файла панели: stroki_fayla.py <файл в C:\\sender\\sender> <с> <по>"""
import io
import sys
т = io.open(r"C:\sender\sender\%s" % sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
for i in range(int(sys.argv[2]) - 1, min(len(т), int(sys.argv[3]))):
    print("%5d: %s" % (i + 1, т[i][:200]))
