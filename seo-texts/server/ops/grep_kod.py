# -*- coding: utf-8 -*-
"""grep по живым файлам панели (только чтение): grep_kod.py <regex> <файл|папка> [контекст]."""
import io
import os
import re
import sys

рег = re.compile(sys.argv[1])
корень = sys.argv[2]
ктх = int(sys.argv[3]) if len(sys.argv) > 3 else 0
файлы = [корень] if os.path.isfile(корень) else [
    os.path.join(d, f) for d, _, фф in os.walk(корень) for f in фф
    if f.endswith(".py") and "tests" not in d and "__pycache__" not in d]
вывод = []
for ф in sorted(файлы):
    try:
        строки = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:  # noqa: BLE001
        continue
    показано = set()
    for i, с in enumerate(строки):
        if рег.search(с):
            for j in range(max(0, i - ктх), min(len(строки), i + ктх + 1)):
                if j not in показано:
                    показано.add(j)
                    вывод.append("%s:%d: %s" % (os.path.relpath(ф, корень) if ф != корень else os.path.basename(ф), j + 1, строки[j][:150]))
            вывод.append("--")
print("\n".join(вывод)[-5800:])
print("=== GREP: %d строк ===" % len(вывод))
