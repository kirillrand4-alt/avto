# -*- coding: utf-8 -*-
"""Положить файл из C:\\sender\\_ops на дроп (для скачивания): v_drop.py <имя_в_ops> [имя_на_дропе]"""
import os, shutil, sys
ист = os.path.join(r"C:\sender\_ops", sys.argv[1]); куда = os.path.join(r"C:\seostat\drop\drop-storage", sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])
shutil.copy2(ист, куда); print("на дропе:", os.path.basename(куда), os.path.getsize(куда))
