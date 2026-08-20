# -*- coding: utf-8 -*-
"""Положить НОВЫЙ модуль в пакет sender, если его там ещё нет.

Новый файл перезаписью чужого не грозит, но проверка обязательна: если
файл уже есть, значит его завела соседняя сессия, и вслепую его трогать
нельзя.
"""
import hashlib
import io
import os
import shutil
import sys

имя = sys.argv[1]
боевой = os.path.join(r"C:\sender\sender", имя)
моё = os.path.join(r"C:\sender\_ops", "MOYO-" + имя)
if os.path.exists(боевой):
    a = hashlib.sha256(io.open(боевой, "rb").read()).hexdigest()[:16]
    b = hashlib.sha256(io.open(моё, "rb").read()).hexdigest()[:16]
    print(f"файл уже есть: боевой {a} | моё {b}")
    if a == b:
        print("одинаковые — ничего не делаю")
        raise SystemExit(0)
    print("РАЗНЫЕ — не трогаю, надо смотреть diff")
    raise SystemExit(2)
shutil.copy2(моё, боевой)
print("положен:", боевой)
import py_compile                                                # noqa: E402
py_compile.compile(боевой, doraise=True)
print("компилируется")
