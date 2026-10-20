# -*- coding: utf-8 -*-
"""Строки лога по регулярке: log_grep.py <путь> <регулярка>"""
import io
import re
import sys
р = re.compile(sys.argv[2])
for s in io.open(sys.argv[1], encoding="utf-8", errors="replace"):
    if р.search(s):
        print(s.rstrip()[:200])
