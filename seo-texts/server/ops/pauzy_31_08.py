# -*- coding: utf-8 -*-
"""Только чтение: точные значения paused/pause_reason и кто их ставил."""
import io
import re
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("=== pause_reason: точные значения ===")
c = Counter()
for р in s.execute("SELECT paused, pause_reason, COUNT(*) n FROM mailbox_state"
                   " GROUP BY paused, pause_reason"):
    print("  paused=%s | reason=%r | %d ящиков"
          % (р["paused"], р["pause_reason"], р["n"]))

print("\n=== ВЫЗОВЫ set_mailbox_paused в коде панели ===")
import glob
import os
for ф in glob.glob(r"C:\sender\sender\*.py"):
    try:
        стр = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        continue
    for i, x in enumerate(стр):
        if "set_mailbox_paused(" in x and "def " not in x:
            куск = " ".join(y.strip() for y in стр[i:i + 4])
            m = re.search(r"set_mailbox_paused\((.{0,110})", куск)
            print("  %-16s:%-5d %s" % (os.path.basename(ф), i + 1,
                                       m.group(1) if m else x.strip()[:100]))

print("\n=== ИТОГ ===")
print("  если reason='1' — значит куда-то ушёл флаг вместо текста причины")
