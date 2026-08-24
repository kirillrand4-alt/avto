# -*- coding: utf-8 -*-
"""Где считается «ждут подтверждения» в боевой панели."""
import glob
import io
import os
import re

# 1) в собранном фронте
файлы = glob.glob(r"C:\sender\web\dist\assets\*.js")
print("бандлов: %d" % len(файлы))
for п in файлы:
    т = io.open(п, encoding="utf-8", errors="replace").read()
    for м in re.finditer("ждут подтверждени", т):
        а = max(0, м.start() - 420)
        print("\n=== %s @%d ===" % (os.path.basename(п), м.start()))
        print(т[а:м.end() + 120].replace("\n", " "))

# 2) в питоне панели
print("\n=== ПИТОН ПАНЕЛИ ===")
for корень, _, имена in os.walk(r"C:\sender\sender"):
    if "__pycache__" in корень or "tests" in корень:
        continue
    for имя in имена:
        if not имя.endswith(".py") or ".bak" in имя:
            continue
        п = os.path.join(корень, имя)
        try:
            т = io.open(п, encoding="utf-8").read()
        except Exception:  # noqa: BLE001
            continue
        for м in re.finditer(r"ждут подтвержд|awaiting_confirm|confirm_waiting"
                             r"|pending_confirm", т):
            н = т[:м.start()].count("\n") + 1
            строка = т.split("\n")[н - 1].strip()
            print("  %s:%d  %s" % (имя, н, строка[:130]))
