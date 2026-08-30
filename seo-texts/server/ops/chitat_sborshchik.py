# -*- coding: utf-8 -*-
"""Читаю daily_collect.py: дедуп по csv, работа с пулом ключей, аргументы."""
import io
import os
import re

п = r"C:\seostat\Parser2\scripts\daily_collect.py"
т = io.open(п, encoding="utf-8", errors="replace").read()
строки = т.splitlines()
print("всего строк: %d" % len(строки))
интерес = (r"add_argument|existing|seen|dedup|csv|key|pool|okved_file|"
           r"page|limit|invalid|401|403|sleep|delay|concurrency")
for n, с in enumerate(строки, 1):
    if re.search(интерес, с, re.I):
        print("%4d| %s" % (n, с.rstrip()[:150]))
