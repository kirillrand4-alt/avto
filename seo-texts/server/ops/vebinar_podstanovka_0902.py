# -*- coding: utf-8 -*-
"""Только чтение: где подставляется ИМЯ_ОТПРАВИТЕЛЯ и где приклеивается подпись."""
import io
import os
import re

ФАЙЛЫ = []
for корень in (r"C:\sender\sender",):
    for дп, _, фс in os.walk(корень):
        if "tests" in дп:
            continue
        for ф in фс:
            if ф.endswith(".py"):
                ФАЙЛЫ.append(os.path.join(дп, ф))

print("=== КТО ЗАМЕНЯЕТ ИМЯ_ОТПРАВИТЕЛЯ ===")
for п in ФАЙЛЫ:
    т = io.open(п, encoding="utf-8", errors="replace").read()
    for м in re.finditer(r"ИМЯ_ОТПРАВИТЕЛЯ", т):
        стр = т[:м.start()].count("\n") + 1
        строка = т.splitlines()[стр - 1].strip()
        if any(k in строка for k in ("replace", "sub(", "def ", "=")):
            print("  %s:%d  %s" % (os.path.basename(п), стр, строка[:110]))

print("\n=== ПОДПИСЬ: где приклеивается ===")
for п in ФАЙЛЫ:
    т = io.open(п, encoding="utf-8", errors="replace").read()
    for м in re.finditer(r"(signature|подпись|podpis|footer|С уважением)", т):
        стр = т[:м.start()].count("\n") + 1
        строка = т.splitlines()[стр - 1].strip()
        if строка.startswith("#") or строка.startswith('"""'):
            continue
        if any(k in строка for k in ("def ", "=", "+", "format", "join", "render")):
            print("  %s:%d  %s" % (os.path.basename(п), стр, строка[:110]))
