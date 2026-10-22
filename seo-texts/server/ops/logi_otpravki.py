# -*- coding: utf-8 -*-
"""Логи службы: список файлов C:\\sender\\logs (размер, время) и строки за
сегодня по регулярке из последних N строк крупных логов. Только чтение.
    logi_otpravki.py <регулярка> [N=20000]"""
import glob
import io
import os
import re
import sys
import time
from collections import deque

р = re.compile(sys.argv[1], re.I)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
for п in sorted(glob.glob(r"C:\sender\logs\*"), key=os.path.getmtime):
    print("%-45s %8d КБ  %s" % (os.path.basename(п), os.path.getsize(п) // 1024, time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(п)))))
for п in sorted([x for x in glob.glob(r"C:\sender\**\*.log", recursive=True) + glob.glob(r"C:\sender\**\*.txt", recursive=True) if "_ops" not in x and "drop-storage" not in x and os.path.getmtime(x) > time.time() - 7200], key=os.path.getmtime)[-6:]:
    if "inbox_poll" in п:
        continue
    хв = deque(io.open(п, encoding="utf-8", errors="replace"), maxlen=N)
    нах = [s.rstrip() for s in хв if р.search(s)]
    print("\n== %s: найдено %d" % (os.path.basename(п), len(нах)))
    for s in нах[-15:]:
        print("   ", s[:230])
