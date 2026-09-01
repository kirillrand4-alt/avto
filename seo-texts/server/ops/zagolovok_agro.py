# -*- coding: utf-8 -*-
"""Заголовок и первые строки agro-base.csv + свежесть сбора."""
import io
import os
import time

CSV = r"C:\seostat\Parser2\data\agro-base.csv"
ЛОГ = r"C:\sender\_ops\sbor-agro.log"

with io.open(CSV, encoding="utf-8", errors="replace", newline="") as ф:
    строки = [next(ф) for _ in range(4)]
print("=== ПЕРВЫЕ СТРОКИ agro-base.csv ===")
for с in строки:
    print("   " + с.rstrip()[:300])

print("")
print("=== ФАЙЛ ===")
print("   размер %d Б, изменён %s"
      % (os.path.getsize(CSV),
         time.strftime("%d.%m %H:%M:%S", time.localtime(os.path.getmtime(CSV)))))

print("")
print("=== ХВОСТ ЛОГА СБОРА ===")
if os.path.exists(ЛОГ):
    хв = io.open(ЛОГ, encoding="utf-8", errors="replace").read().splitlines()
    print("   строк в логе: %d, изменён %s"
          % (len(хв), time.strftime("%d.%m %H:%M:%S",
                                    time.localtime(os.path.getmtime(ЛОГ)))))
    for с in хв[-22:]:
        print("   " + с[:170])
else:
    print("   лога нет")
