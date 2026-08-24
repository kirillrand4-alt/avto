# -*- coding: utf-8 -*-
"""Файлы .err отцеплённых запусков — там трейсбеки, которых нет в .log."""
import glob
import io
import os
import time

файлы = sorted(glob.glob(r"C:\sender\_ops\*.err"),
               key=lambda x: -os.path.getmtime(x))[:6]
if not файлы:
    print("файлов .err нет вовсе")
for п in файлы:
    возраст = (time.time() - os.path.getmtime(п)) / 60.0
    print("=== %s (%d байт, %.1f мин назад) ==="
          % (os.path.basename(п), os.path.getsize(п), возраст))
    т = io.open(п, encoding="utf-8", errors="replace").read()
    print(т[-2500:] if т.strip() else "  (пусто)")
    print()
