# -*- coding: utf-8 -*-
"""Почему умер драйвер очереди: логи целиком."""
import glob
import io
import os
import time

for п in sorted(glob.glob(r"C:\sender\_ops\ochered*"),
                key=lambda x: -os.path.getmtime(x)):
    if п.endswith(".py"):
        continue
    print("=== %s (%d байт, обновлён %.1f мин назад) ==="
          % (os.path.basename(п), os.path.getsize(п),
             (time.time() - os.path.getmtime(п)) / 60.0))
    try:
        т = io.open(п, encoding="utf-8", errors="replace").read()
    except Exception as e:  # noqa: BLE001
        print("  не прочитан: %s" % e)
        continue
    for с in т.splitlines()[-40:]:
        print("  %s" % с[:190])
    print()

print("=== ХВОСТ panel_err.log (вдруг панель ругалась) ===")
try:
    строки = io.open(r"C:\sender\_ops\panel_err.log", encoding="utf-8",
                     errors="replace").readlines()
    for с in строки[-12:]:
        print("  %s" % с.rstrip()[:190])
except Exception as e:  # noqa: BLE001
    print("  %s" % e)
