# -*- coding: utf-8 -*-
"""Поиск в исходниках фронта панели (C:\\sender\\sender\\web\\src) и дата
изменения файла: web_grep.py <регулярка> [контекст=3]"""
import glob
import io
import os
import re
import sys
import time
р = re.compile(sys.argv[1])
к = int(sys.argv[2]) if len(sys.argv) > 2 else 3
for п in sorted(glob.glob(r"C:\sender\sender\web\src\**\*.ts*", recursive=True)):
    т = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for i, s in enumerate(т):
        if р.search(s):
            print("==== %s:%d (изменён %s)" % (п.split("web\\src\\")[-1], i + 1, time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(п)))))
            for j in range(max(0, i - к), min(len(т), i + к + 1)):
                print("   %d: %s" % (j + 1, т[j][:170]))
