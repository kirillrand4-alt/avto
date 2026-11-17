# -*- coding: utf-8 -*-
"""Скопировать файл из C:\\sender\\_ops на дроп (C:\\seostat\\drop\\drop-storage) для скачивания: na_drop_iz_ops.py <имя>"""
import os, shutil, sys
и = os.path.basename(sys.argv[1])
shutil.copyfile(os.path.join(r"C:\sender\_ops", и), os.path.join(r"C:\seostat\drop\drop-storage", и))
print("на дропе:", и, os.path.getsize(os.path.join(r"C:\seostat\drop\drop-storage", и)))
