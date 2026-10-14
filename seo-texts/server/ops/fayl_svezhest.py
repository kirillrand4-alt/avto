# -*- coding: utf-8 -*-
"""Размер и время изменения файлов: fayl_svezhest.py <путь> [<путь>...]"""
import os
import sys
import time
for п in sys.argv[1:]:
    if os.path.exists(п):
        print("%s: %d байт, изменён %s" % (п, os.path.getsize(п), time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
    else:
        print("%s: нет" % п)
print("сейчас %s" % time.strftime("%H:%M:%S"))
print("=== СВЕЖЕСТЬ ===")
