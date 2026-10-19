# -*- coding: utf-8 -*-
"""Время сервера и размер/время изменения файлов: vremya_i_hvost.py <путь>..."""
import os
import sys
import time
print("сейчас на сервере:", time.strftime("%Y-%m-%d %H:%M:%S"))
for п in sys.argv[1:]:
    if os.path.exists(п):
        print(п, os.path.getsize(п), "изм.", time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п))))
