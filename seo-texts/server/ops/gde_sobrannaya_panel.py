# -*- coding: utf-8 -*-
"""Где лежит собранный SPA панели и когда он собран."""
import os
import time

КАНДИДАТЫ = [r"C:\sender\sender\web\dist", r"C:\sender\web\dist",
             r"C:\sender\sender\api\static", r"C:\sender\static",
             r"C:\sender\dist"]
for п in КАНДИДАТЫ:
    if not os.path.isdir(п):
        continue
    print("--- %s ---" % п)
    for корень, папки, файлы in os.walk(п):
        for ф in файлы[:20]:
            полный = os.path.join(корень, ф)
            print("   %-46s %8d б  %s"
                  % (полный[len(п) + 1:][:46], os.path.getsize(полный),
                     time.strftime("%m-%d %H:%M",
                                   time.localtime(os.path.getmtime(полный)))))
        if корень.count(os.sep) - п.count(os.sep) > 1:
            break
print("")
print("=" * 74)
print("=== ГДЕ СОБРАННАЯ ПАНЕЛЬ ===")
