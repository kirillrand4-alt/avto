# -*- coding: utf-8 -*-
"""Что за KK.модель у допоиска Meyer-7."""
import io
import re
т = io.open(r"C:\sender\server\meyer7_dopoisk.py", encoding="utf-8").read()
for с in т.splitlines():
    if re.search(r"import .*KK|KK\s*=|as KK", с):
        print("   " + с.strip())
м = re.search(r"from\s+(\S+)\s+import\s+.*\bKK\b|import\s+(\S+)\s+as\s+KK", т)
имя = (м.group(1) or м.group(2)) if м else ""
print("модуль KK: %s" % имя)
import os
for п in (r"C:\sender\server\%s.py" % имя.split(".")[-1], r"C:\sender\%s.py" % имя.split(".")[-1]):
    if имя and os.path.exists(п):
        к = io.open(п, encoding="utf-8", errors="replace").read()
        for с in к.splitlines():
            if re.search(r"^\s*(модель|МОДЕЛЬ|MODEL)\w*\s*=", с):
                print("   %s: %s" % (os.path.basename(п), с.strip()[:150]))
print("=== KK ===")
