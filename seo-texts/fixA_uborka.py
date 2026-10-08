# -*- coding: utf-8 -*-
"""Исправитель A: убрать СВОИ временные файлы на сервере (копии базы продаж для рендера,
рабочую папку шаблонов). Бэкапы правок C:\\centro2\\_bekap\\fixA-2026* не трогаются.

    python3 zapusk_na_servere.py fixA_uborka.py
"""
import glob
import os
import shutil

B = r'C:\centro2\_bekap'
for p in glob.glob(os.path.join(B, 'fixA-render-*.db')) + glob.glob(os.path.join(B, 'fixA-test-*.db')):
    try:
        os.remove(p)
        print('удалён', os.path.basename(p))
    except OSError as e:
        print('не удалён', os.path.basename(p), e)
st = os.path.join(B, 'fixA-stage')
if os.path.isdir(st):
    shutil.rmtree(st, ignore_errors=True)
    print('удалена рабочая папка', os.path.basename(st))
print('бэкапы правок:', sorted(os.path.basename(x) for x in glob.glob(os.path.join(B, 'fixA-2026*'))))
