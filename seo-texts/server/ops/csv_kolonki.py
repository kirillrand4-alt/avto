# -*- coding: utf-8 -*-
"""Названия колонок CSV на дропе и доля заполненных (значения не печатаем).  csv_kolonki.py <имя.csv>"""
import csv, io, os, sys
csv.field_size_limit(10 ** 9)
р = list(csv.DictReader(io.open(os.path.join(r"C:\seostat\drop\drop-storage", sys.argv[1]), encoding="utf-8-sig", errors="replace"), delimiter=";"))
print("строк:", len(р))
for к in (р[0].keys() if р else []):
    print("  %-40s заполнено %d" % (к, sum(1 for x in р if (x.get(к) or "").strip())))
