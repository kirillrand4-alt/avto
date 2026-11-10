# -*- coding: utf-8 -*-
"""Файлы по маске на сервере: spisok_faylov.py 'C:\\sender\\_ops\\lesenka-roli-*.json'. Только чтение."""
import glob, os, sys
for п in sorted(glob.glob(sys.argv[1])): print(os.path.getsize(п), п)
