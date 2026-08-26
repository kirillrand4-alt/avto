# -*- coding: utf-8 -*-
"""Поставить разбор таблиц в pismo_v_tekst. Заменяем целиком со сверкой."""
import io
import os
import py_compile
import shutil
import sys
import time

КАТИТЬ = "--katit" in sys.argv
БОЕВОЙ = r"C:\sender\sender\pismo_v_tekst.py"
НОВЫЙ = r"C:\sender\_ops\_novyy_pismo_v_tekst.py"
МЕТКА = "tablicy_v_stroki"

т = io.open(БОЕВОЙ, encoding="utf-8", errors="replace").read()
нт = io.open(НОВЫЙ, encoding="utf-8", errors="replace").read()
if МЕТКА in т:
    print("правка уже стоит")
    raise SystemExit(0)
if МЕТКА not in нт:
    raise SystemExit("в заготовке нет правки")
свои = set(нт.splitlines())
пропало = [с for с in т.splitlines() if с.strip() and с not in свои]
if пропало:
    print("ЗАТРЁМ %d строк боевого — не трогаю:" % len(пропало))
    for с in пропало[:10]:
        print("   " + с[:140])
    raise SystemExit(1)
print("боевой (%d знаков) целиком в заготовке (%d)" % (len(т), len(нт)))
if not КАТИТЬ:
    print("\nсухой прогон. Катить: --katit")
    raise SystemExit(0)
копия = "%s.bak-%d" % (БОЕВОЙ, int(time.time()))
shutil.copy2(БОЕВОЙ, копия)
shutil.copy2(НОВЫЙ, БОЕВОЙ)
py_compile.compile(БОЕВОЙ, doraise=True)
print("поставлен (.bak %s)" % os.path.basename(копия))
