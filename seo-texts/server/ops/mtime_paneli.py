# -*- coding: utf-8 -*-
"""Даты изменения файлов панели и их бэкапов по маске: mtime_paneli.py <маска>"""
import glob
import os
import sys
import time
for п in sorted(glob.glob(r"C:\sender\sender\%s" % sys.argv[1]), key=os.path.getmtime):
    print(time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(п))), os.path.basename(п))
