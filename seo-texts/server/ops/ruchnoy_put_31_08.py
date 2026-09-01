# -*- coding: utf-8 -*-
"""Только чтение: ручной путь approve -> отправка, что он пишет."""
import io
import os
import re

for ф in (r"C:\sender\sender\confirm.py",):
    стр = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    print("=== %s: %d строк ===" % (os.path.basename(ф), len(стр)))
    for i, x in enumerate(стр):
        if re.match(r"\s*def (approve|_approve|send_now|_send)", x):
            print("  %4d  %s" % (i + 1, x.strip()[:100]))

    н = [i for i, x in enumerate(стр) if re.match(r"\s*def approve", x)]
    for i in н:
        print("\n=== approve, %d строк ===" % (i + 1))
        for j in range(i, min(i + 70, len(стр))):
            print("  %4d  %s" % (j + 1, стр[j][:110]))

print("\n=== ИТОГ: кто пишет событие sent ===")
import glob
for ф in glob.glob(r"C:\sender\sender\*.py"):
    стр = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    for i, x in enumerate(стр):
        if re.search(r"""["']sent["']""", x) and re.search(r"(event|add_event|log_event)", x):
            print("  %-14s:%-5d %s" % (os.path.basename(ф), i + 1, x.strip()[:96]))
