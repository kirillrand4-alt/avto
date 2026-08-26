# -*- coding: utf-8 -*-
"""Поставить гейт адресата с правилом про конкурента.

Заменяем целиком, сверив, что боевая копия отличается от заготовки ТОЛЬКО
нашей вставкой: каталог делят несколько сессий.
"""
import hashlib
import io
import os
import py_compile
import shutil
import sys
import time

КАТИТЬ = "--katit" in sys.argv
БОЕВОЙ = r"C:\sender\sender\target_gate.py"
НОВЫЙ = r"C:\sender\_ops\_novyy_target_gate.py"
МЕТКА = "КОНКУРЕНТ - НЕ ПОКУПАТЕЛЬ"

т = io.open(БОЕВОЙ, encoding="utf-8", errors="replace").read()
нт = io.open(НОВЫЙ, encoding="utf-8", errors="replace").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
if МЕТКА not in нт:
    raise SystemExit("в заготовке нет правки")
print("боевой %d знаков, sha %s"
      % (len(т), hashlib.sha1(io.open(БОЕВОЙ, "rb").read()).hexdigest()[:12]))
print("заготовка %d знаков" % len(нт))
# Всё, что есть в боевом, обязано быть и в заготовке: иначе соседняя сессия
# что-то дописала, и замена это затрёт.
пропало = [с for с in т.splitlines()
           if с.strip() and с not in нт.splitlines()]
if пропало:
    print("ЗАТРЁМ %d строк боевого — не трогаю:" % len(пропало))
    for с in пропало[:10]:
        print("   " + с[:140])
    raise SystemExit(1)
print("боевой целиком содержится в заготовке — замена безопасна")
if not КАТИТЬ:
    print("\nсухой прогон. Катить: --katit")
    raise SystemExit(0)
копия = "%s.bak-%d" % (БОЕВОЙ, int(time.time()))
shutil.copy2(БОЕВОЙ, копия)
shutil.copy2(НОВЫЙ, БОЕВОЙ)
py_compile.compile(БОЕВОЙ, doraise=True)
print("поставлен (.bak %s)" % os.path.basename(копия))
