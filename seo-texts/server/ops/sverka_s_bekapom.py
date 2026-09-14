# -*- coding: utf-8 -*-
"""Сверка нового конфига с бэкапом: не убрали ли лишнего."""
import glob
import io
import os
import re
import sys

ФАЙЛ = r"C:\sender\sender.yaml"
бэкапы = sorted(glob.glob(ФАЙЛ + ".bak-*"), key=os.path.getmtime)
if not бэкапы:
    raise SystemExit("бэкапов нет")
БЭК = бэкапы[-1]
print("сверяем с %s" % os.path.basename(БЭК))

def раздел_ящиков(текст, имя):
    вкл, вых = False, []
    for с in текст.splitlines():
        if с.startswith(имя + ":"):
            вкл = True
            continue
        if вкл and re.match(r"^[^\s#]", с):
            break
        if вкл:
            м = re.match(r"^\s+([^\s:]+@[^\s:]+):\s*(\S+)\s*$", с)
            if м:
                вых.append(м.group(1))
    return вых

было = io.open(БЭК, encoding="utf-8").read()
стало = io.open(ФАЙЛ, encoding="utf-8").read()
б = раздел_ящиков(было, "personalization")
с = раздел_ящиков(стало, "personalization")
print("")
print("--- personalization ---")
print("   было %d, стало %d" % (len(б), len(с)))
print("   убрали: %s" % ", ".join(x for x in б if x not in с))
print("   остались: %s" % ", ".join(с))
лишние = [x for x in б if x not in с and "ompressor" not in x]
print("   убрали НЕ компрессорных: %d %s" % (len(лишние), лишние))

# построчная разница целиком
бс, сс = было.splitlines(), стало.splitlines()
только_было = [x for x in бс if x not in сс]
только_стало = [x for x in сс if x not in бс]
print("")
print("--- строк исчезло: %d, появилось: %d ---" % (len(только_было), len(только_стало)))
не_кц = [x for x in только_было
         if "ompressor" not in x and x.strip() and not x.strip().startswith("#")]
print("")
print("--- исчезнувшие строки БЕЗ компрессорных доменов (%d) ---" % len(не_кц))
for x in не_кц[:40]:
    print("   | %s" % x[:130])
print("")
print("--- появившиеся строки ---")
for x in только_стало[:12]:
    print("   | %s" % x[:130])
print("")
print("=" * 74)
print("=== СВЕРКА С БЭКАПОМ ===")
