# -*- coding: utf-8 -*-
"""Простейший оп: жив ли вообще путь «панель -> питон -> stdout».

После перезапуска партии задания стали падать за доли секунды с
returncode 4294967295 и пустым выводом — включая безобидную читалку
файлов, которая работала сорока минутами раньше. Значит дело не в
скрипте. Здесь ничего не импортируется и не запускается: печать, место
на диске, память.
"""
import os
import shutil
import sys

print("жив, питон", sys.version.split()[0])
try:
    в, занято, свободно = shutil.disk_usage(r"C:\sender")
    print("диск C:\\sender — всего %.1f ГБ, свободно %.1f ГБ"
          % (в / 2**30, свободно / 2**30))
except Exception as e:                                         # noqa: BLE001
    print("место не прочиталось:", e)
try:
    print("файлов в _ops:", len(os.listdir(r"C:\sender\_ops")))
except Exception as e:                                         # noqa: BLE001
    print("_ops не прочитался:", e)
