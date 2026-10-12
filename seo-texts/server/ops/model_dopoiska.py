# -*- coding: utf-8 -*-
"""На какой модели идёт meyer7_dopoisk.py (соседнее задание) и что он делает."""
import io
import os
import re
import time
п = r"C:\sender\server\meyer7_dopoisk.py"
т = io.open(п, encoding="utf-8", errors="replace").read()
print("файл %d байт, изменён %s" % (len(т), time.strftime(
    "%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(п)))))
print("--- шапка ---")
print(т[:900])
print("--- модели в коде ---")
for м in sorted(set(re.findall(r"claude-[a-z0-9\-]+|gpt-[a-z0-9\.\-]+", т))):
    print("   " + м)
for с in т.splitlines():
    if re.search(r"(?i)model\s*=|МОДЕЛ\w*\s*=|--model", с) and len(с) < 160:
        print("   > " + с.strip())
print("=== ДОПОИСК ===")
