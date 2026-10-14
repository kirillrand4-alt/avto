# -*- coding: utf-8 -*-
"""Скопировать файл из C:\\sender\\_ops на дроп: ops_na_drop.py <имя>"""
import shutil
import sys
for ф in sys.argv[1:]:
    shutil.copy2(r"C:\sender\_ops" + "\\" + ф, r"C:\seostat\drop\drop-storage" + "\\" + "ops_" + ф)
    print("на дропе: ops_" + ф)
print("=== OPS НА ДРОП ===")
