# -*- coding: utf-8 -*-
"""Хвост самого свежего лога генерации."""
import glob
import io
import os
import time

логи = glob.glob(r"C:\sender\_ops\partiya_gen-*.log") + glob.glob(
    r"C:\sender\_ops\ochered*.log")
логи = [п for п in логи if os.path.isfile(п)]
логи.sort(key=os.path.getmtime, reverse=True)
for п in логи[:2]:
    print("==== %s (%.0f мин назад, %d б) ====" % (
        os.path.basename(п), (time.time() - os.path.getmtime(п)) / 60,
        os.path.getsize(п)))
    строки = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for с in строки[-18:]:
        print("   " + с[:165])
    оши = os.path.splitext(п)[0] + ".err"
    if os.path.exists(оши) and os.path.getsize(оши):
        т = io.open(оши, encoding="utf-8", errors="replace").read().strip()
        print("   --- ошибки (%d б), хвост ---" % len(т))
        for с in т.splitlines()[-6:]:
            print("   " + с[:165])
    print("")
