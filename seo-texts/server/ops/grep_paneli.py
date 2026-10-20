# -*- coding: utf-8 -*-
"""Поиск строки в коде панели (C:\\sender\\sender\\*.py): grep_paneli.py <регулярка> [контекст=2]"""
import glob
import io
import re
import sys
рег = re.compile(sys.argv[1])
к = int(sys.argv[2]) if len(sys.argv) > 2 else 2
for п in sorted(glob.glob(r"C:\sender\sender\*.py")):
    т = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for i, s in enumerate(т):
        if рег.search(s):
            print("==== %s:%d" % (п.split("\\")[-1], i + 1))
            for j in range(max(0, i - к), min(len(т), i + к + 1)):
                print("   %d: %s" % (j + 1, т[j][:170]))
