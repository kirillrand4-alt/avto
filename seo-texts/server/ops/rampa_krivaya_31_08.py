# -*- coding: utf-8 -*-
"""Только чтение: кривая рампы (начало _daily_limit)."""
import io
import re

стр = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
              errors="replace").read().splitlines()
н = None
for i, x in enumerate(стр):
    if re.match(r"\s*def _daily_limit", x):
        н = i
        break
for i in range(н, min(н + 30, len(стр))):
    print("  %4d  %s" % (i + 1, стр[i][:112]))
