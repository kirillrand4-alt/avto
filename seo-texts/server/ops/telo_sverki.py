# -*- coding: utf-8 -*-
"""Тело sverka_prigovorov целиком + хвост её лога: сколько на самом деле идёт."""
import io
import os
import time

П = r"C:\sender\server\ops\sverka_prigovorov.py"
ЛОГ = r"C:\sender\_ops\sverka-prigovorov.log"

print("=== ТЕЛО sverka_prigovorov.py ===")
т = io.open(П, encoding="utf-8", errors="replace").read().splitlines()
внутри_шапки = False
for i, с in enumerate(т, 1):
    if i <= 20 and '"""' in с:
        внутри_шапки = not внутри_шапки
        continue
    if внутри_шапки:
        continue
    print("%4d| %s" % (i, с[:140]))

print("")
print("=== ХВОСТ ЛОГА %s ===" % ЛОГ)
if os.path.exists(ЛОГ):
    стр = io.open(ЛОГ, encoding="utf-8", errors="replace").read().splitlines()
    print("   строк %d, изменён %s"
          % (len(стр), time.strftime("%d.%m %H:%M:%S",
                                     time.localtime(os.path.getmtime(ЛОГ)))))
    for с in стр[-40:]:
        print("   " + с[:150])
else:
    print("   лога нет")
