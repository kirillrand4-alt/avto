# -*- coding: utf-8 -*-
"""Убрать STOP-файл дирижёра яруса C (_ops/v4c-pachki.STOP), чтобы его можно было запустить снова."""
import os
п = r"C:\sender\_ops\v4c-pachki.STOP"
if os.path.exists(п):
    os.remove(п)
    print("STOP убран")
else:
    print("STOP-файла нет")
