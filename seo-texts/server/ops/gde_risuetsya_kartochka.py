# -*- coding: utf-8 -*-
"""Где на экране подтверждения рисуется блок «Кому пишем», и что новее
сборки фронта (чтобы пересборка не притащила чужие незаконченные правки)."""
import io
import os
import re
import time

КОРЕНЬ = r"C:\sender\sender\web\src"
сборка = os.path.getmtime(r"C:\sender\sender\web\dist\index.html") \
    if os.path.exists(r"C:\sender\sender\web\dist\index.html") else 0
print("сборка dist: %s" % time.strftime("%Y-%m-%d %H:%M", time.localtime(сборка)))
новее = []
for папка, _, файлы in os.walk(КОРЕНЬ):
    for ф in файлы:
        п = os.path.join(папка, ф)
        if os.path.getmtime(п) > сборка + 60:
            новее.append((п, os.path.getmtime(п)))
print("исходников новее сборки: %d" % len(новее))
for п, м in sorted(новее, key=lambda x: -x[1])[:10]:
    print("   %s  %s" % (time.strftime("%m-%d %H:%M", time.localtime(м)),
                         п.replace(КОРЕНЬ, "src")))
print("")
for папка, _, файлы in os.walk(КОРЕНЬ):
    for ф in файлы:
        if not ф.endswith(".tsx"):
            continue
        п = os.path.join(папка, ф)
        т = io.open(п, encoding="utf-8", errors="replace").read()
        if "Кому пишем" in т or "почтовый сервер" in т:
            print("### %s" % п.replace(КОРЕНЬ, "src"))
            for м in re.finditer(r".{0,100}(Кому пишем|откуда знаем|почтовый сервер).{0,140}", т):
                print("   …%s…" % м.group(0).replace("\n", "⏎")[:240])
print("")
print("=== ГДЕ РИСУЕТСЯ КАРТОЧКА ===")
