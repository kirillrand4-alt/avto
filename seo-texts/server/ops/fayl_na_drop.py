# -*- coding: utf-8 -*-
"""Любой файл на дроп плоским именем: fayl_na_drop.py <полный путь> <имя на дропе>"""
import shutil, sys
shutil.copy2(sys.argv[1], r"C:\seostat\drop\drop-storage" + "\\" + sys.argv[2]); print("на дропе:", sys.argv[2])
