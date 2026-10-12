# -*- coding: utf-8 -*-
"""Не потеряла ли пересборка фронта что-то из старого бандла.

Новый бандл на 17 КБ меньше старого — проверяем по строкам интерфейса:
какие русские надписи были в старом и пропали в новом.
"""
import glob
import io
import os
import re
import sys

метка = sys.argv[1] if len(sys.argv) > 1 else ""
старые = glob.glob(r"C:\sender\sender\web\dist.bak-%s\assets\index-*.js" % метка)
новые = glob.glob(r"C:\sender\sender\web\dist\assets\index-*.js")
стар = [п for п in старые if not п.endswith(".map")][0]
нов = [п for п in новые if not п.endswith(".map")][0]
print("старый: %s %d" % (os.path.basename(стар), os.path.getsize(стар)))
print("новый:  %s %d" % (os.path.basename(нов), os.path.getsize(нов)))


def строки(п):
    т = io.open(п, encoding="utf-8", errors="replace").read()
    return set(re.findall(r"[А-Яа-яЁё][А-Яа-яЁё ,.:«»\-]{6,60}", т))


а, б = строки(стар), строки(нов)
пропало = sorted(а - б)
появилось = sorted(б - а)
print("русских строк: было %d, стало %d" % (len(а), len(б)))
print("пропало: %d" % len(пропало))
for с in пропало[:40]:
    print("   - %s" % с)
print("появилось: %d" % len(появилось))
for с in появилось[:15]:
    print("   + %s" % с)
print("=== СРАВНЕНИЕ БАНДЛОВ ===")
