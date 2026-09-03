# -*- coding: utf-8 -*-
"""Как устроен мост в зенку: что читает, куда пишет, в каком виде задания."""
import io
import os
import re

П = r"C:\sender\server\zenno_most.py"
т = io.open(П, encoding="utf-8", errors="replace").read()
стр = т.splitlines()

print("=== %s: %d строк ===" % (os.path.basename(П), len(стр)))
м = re.search(r'"""(.*?)"""', т, re.S)
print("--- шапка ---")
print((м.group(1).strip()[:2200]) if м else "шапки нет")

print("")
print("--- функции ---")
for м2 in re.finditer(r"^def\s+([a-zA-Zа-яА-Я0-9_]+)\(([^)]{0,70})", т, re.M):
    print("   %s(%s)" % (м2.group(1), м2.group(2)[:60]))

print("")
print("--- пути, таблицы, очереди ---")
for м3 in re.finditer(r"r?['\"]([A-Za-z]:\\\\?[^'\"]{4,90})['\"]", т):
    print("   путь: %s" % м3.group(1))
for м4 in re.finditer(r"(FROM|INTO|UPDATE)\s+([a-zA-Z_]+)", т):
    print("   таблица: %s %s" % (м4.group(1), м4.group(2)))

print("")
print("--- первые 60 строк ---")
for i, с in enumerate(стр[:60], 1):
    print("%4d| %s" % (i, с[:140]))
