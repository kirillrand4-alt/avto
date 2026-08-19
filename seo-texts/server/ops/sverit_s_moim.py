# -*- coding: utf-8 -*-
"""Сравнить серверный файл пакета sender с моей копией — построчный diff.

Скачивать 149КБ через хвост stdout бессмысленно (обрежется), а знать, чем
серверная копия отличается от моей, обязательно: каталог общий с соседней
сессией, и вслепую перезаписать её правку нельзя.

Мою копию кладём рядом в _ops под именем МОЁ-<имя>, здесь только читаем.
"""
import difflib
import io
import os
import sys

имя = sys.argv[1]
серверный = os.path.join(r"C:\sender\sender", имя.replace("/", os.sep))
моё = os.path.join(r"C:\sender\_ops", "MOYO-" + os.path.basename(имя))

a = io.open(серверный, encoding="utf-8", errors="replace").read().splitlines()
b = io.open(моё, encoding="utf-8", errors="replace").read().splitlines()
print(f"сервер: {len(a)} строк | моё: {len(b)} строк")

diff = list(difflib.unified_diff(a, b, fromfile="СЕРВЕР", tofile="МОЁ",
                                 lineterm="", n=2))
if not diff:
    print("РАЗЛИЧИЙ НЕТ")
else:
    print(f"различий в diff: {len(diff)} строк")
    for s in diff[:400]:
        print(s)
    if len(diff) > 400:
        print(f"... ещё {len(diff) - 400} строк diff")
