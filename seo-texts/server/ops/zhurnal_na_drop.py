# -*- coding: utf-8 -*-
"""Копия журнала _ops на дроп: zhurnal_na_drop.py <имя файла в _ops>"""
import shutil
import sys
shutil.copy2(r"C:\sender\_ops" + "\\" + sys.argv[1], r"C:\seostat\drop\drop-storage" + "\\" + "ops_" + sys.argv[1])
print("=== ЖУРНАЛ НА ДРОП ===")
