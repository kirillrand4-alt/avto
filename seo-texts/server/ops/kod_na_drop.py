# -*- coding: utf-8 -*-
"""Скопировать модули панели на дроп для сверки: kod_na_drop.py confirm.py sender.py ..."""
import shutil
import sys
for ф in sys.argv[1:]:
    shutil.copy2(r"C:\sender\sender" + "\\" + ф, r"C:\seostat\drop\drop-storage" + "\\" + "srv_" + ф)
    print("на дропе: srv_" + ф)
print("=== КОД НА ДРОП ===")
