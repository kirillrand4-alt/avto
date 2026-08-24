# -*- coding: utf-8 -*-
"""Первые строки лога прогона: с какой моделью и порогом он реально пошёл.

В списке процессов кириллические аргументы показались как «?????=1.5» -
это может быть и особенность вывода, и настоящая порча аргументов при
передаче. Разница важная: без «модель=» прогон возьмёт модель по умолчанию.
"""
import glob
import io
import os

файлы = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
               key=os.path.getmtime, reverse=True)[:2]
for п in файлы:
    print(f"=== {os.path.basename(п)} ({os.path.getsize(п)} байт) ===")
    print(io.open(п, encoding="utf-8", errors="replace").read()[:1500])
    print()
