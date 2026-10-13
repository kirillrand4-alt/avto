# -*- coding: utf-8 -*-
"""Файлы _ops по маске, изменённые за N часов: fayly_ops_segodnya.py <кусок> [chasov=6]"""
import glob
import os
import sys
import time
К = sys.argv[1]
Ч = float(dict(а.split("=", 1) for а in sys.argv[2:] if "=" in а).get("chasov", "6"))
for п in sorted(glob.glob(r"C:\sender\_ops\*"), key=os.path.getmtime):
    if К in os.path.basename(п) and time.time() - os.path.getmtime(п) < Ч * 3600:
        print("%s %8d КБ %s" % (time.strftime("%H:%M", time.localtime(os.path.getmtime(п))), os.path.getsize(п) // 1024, п))
print("=== ФАЙЛЫ ===")
