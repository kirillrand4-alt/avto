# -*- coding: utf-8 -*-
"""Только чтение: Sender._otkaz_spam — что именно паузит при отказе."""
import io
import re

стр = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
              errors="replace").read().splitlines()
н = [i for i, x in enumerate(стр) if re.search(r"def _otkaz_spam", x)]
print("=== найдено на строках: %s ===" % [i + 1 for i in н])
for i in н:
    отступ = len(стр[i]) - len(стр[i].lstrip())
    for j in range(i, min(i + 60, len(стр))):
        x = стр[j]
        if j > i and x.strip() and (len(x) - len(x.lstrip())) <= отступ \
                and x.lstrip().startswith("def "):
            break
        print("  %4d  %s" % (j + 1, x[:108]))
