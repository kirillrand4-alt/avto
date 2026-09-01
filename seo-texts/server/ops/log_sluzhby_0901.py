# -*- coding: utf-8 -*-
"""Только чтение: свежие логи службы, ищем ошибки тика."""
import glob
import io
import os
from datetime import datetime

канд = []
for шаб in (r"C:\sender\*.log", r"C:\sender\logs\*.log", r"C:\sender\sender\*.log",
            r"C:\sender\_ops\*.log"):
    канд += glob.glob(шаб)
канд = sorted(канд, key=os.path.getmtime, reverse=True)[:6]
print("=== СВЕЖИЕ ЛОГИ ===")
for л in канд:
    т = datetime.fromtimestamp(os.path.getmtime(л))
    print("  %s  %8d б  %s" % (т.strftime("%H:%M:%S"), os.path.getsize(л),
                               os.path.basename(л)))

print("\n=== ХВОСТЫ (последние 12 строк каждого) ===")
for л in канд[:4]:
    print("\n  --- %s ---" % os.path.basename(л))
    try:
        стр = io.open(л, encoding="utf-8", errors="replace").read().splitlines()
        for x in стр[-12:]:
            print("     " + x[:118])
    except Exception as ex:
        print("     ", str(ex)[:70])

print("\n=== ИТОГ: ПОИСК ОШИБОК ЗА СЕГОДНЯ ===")
for л in канд[:4]:
    try:
        стр = io.open(л, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        continue
    плохо = [x for x in стр[-400:]
             if any(k in x.lower() for k in ("error", "traceback", "exception",
                                             "ошибк", "не смог", "failed"))]
    if плохо:
        print("  --- %s: %d строк с ошибками, последние 6 ---"
              % (os.path.basename(л), len(плохо)))
        for x in плохо[-6:]:
            print("     " + x[:118])
