# -*- coding: utf-8 -*-
"""Полный текст сбоев предклассификатора в свежем логе."""
import glob
import io
import os
import time

п = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
           key=os.path.getmtime, reverse=True)[0]
print("лог: %s (%.1f мин назад)" % (os.path.basename(п),
                                    (time.time() - os.path.getmtime(п)) / 60))
с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
from collections import Counter
сбои = Counter()
for x in с:
    if "споткнулся" in x:
        сбои[x.strip()[:150]] += 1
print("=== РАЗНЫЕ СБОИ ПРЕДКЛАССИФИКАТОРА ===")
for т_, n in сбои.most_common(10):
    print("   %3d  %s" % (n, т_))
print("\n--- последние 10 строк лога ---")
for x in с[-10:]:
    print("   %s" % x.strip()[:200])

# что реально лежит в задеплоенном файле
f = io.open(r"C:\sender\_ops\partiya_gen.py", encoding="utf-8").read()
for стр in f.splitlines():
    if "_ПРЕДКЛАСС_МОДЕЛЬ =" in стр or "_ПРЕДКЛАСС_ЗАПАС = " in стр:
        print("\nв файле: %s" % стр.strip())
