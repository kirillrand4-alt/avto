# -*- coding: utf-8 -*-
"""Только .err драйвера очереди."""
import glob
import io
import os
import time

for п in sorted(glob.glob(r"C:\sender\_ops\ochered_vladeltsa-*.err"),
                key=lambda x: -os.path.getmtime(x)):
    print("=== %s (%d байт, %.1f мин назад) ==="
          % (os.path.basename(п), os.path.getsize(п),
             (time.time() - os.path.getmtime(п)) / 60.0))
    т = io.open(п, encoding="utf-8", errors="replace").read()
    print(т[-2500:] if т.strip() else "  (ПУСТО — значит процесс не падал, его убили)")
    print()
