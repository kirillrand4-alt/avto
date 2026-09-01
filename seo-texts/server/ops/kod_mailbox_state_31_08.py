# -*- coding: utf-8 -*-
"""Только чтение: где в коде панели заводится и обновляется mailbox_state."""
import glob
import io
import os
import re

КОРЕНЬ = r"C:\sender\sender"
файлы = glob.glob(os.path.join(КОРЕНЬ, "*.py"))
print("=== файлов в %s: %d ===" % (КОРЕНЬ, len(файлы)))

инт = ("mailbox_state", "ramp_day", "daily_limit", "pause_reason")
где = {}
for ф in файлы:
    try:
        t = io.open(ф, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for к in инт:
        n = t.count(к)
        if n:
            где.setdefault(os.path.basename(ф), {})[к] = n
print("\n=== ГДЕ УПОМИНАЮТСЯ ===")
for ф, d in sorted(где.items(), key=lambda x: -sum(x[1].values())):
    print("  %-24s %s" % (ф, d))

print("\n=== INSERT/UPSERT В mailbox_state ===")
for ф in файлы:
    try:
        t = io.open(ф, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    if "mailbox_state" not in t:
        continue
    стр = t.splitlines()
    for i, x in enumerate(стр):
        if re.search(r"(INSERT|REPLACE|UPDATE).{0,60}mailbox_state", x, re.I):
            print("\n  --- %s:%d ---" % (os.path.basename(ф), i + 1))
            for y in стр[max(0, i - 6):i + 14]:
                print("    " + y[:118])

print("\n=== ИТОГ: где задаётся daily_limit ===")
for ф in файлы:
    try:
        t = io.open(ф, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    стр = t.splitlines()
    for i, x in enumerate(стр):
        if re.search(r"daily_limit\s*=", x) and "self" not in x[:12]:
            print("  %s:%d  %s" % (os.path.basename(ф), i + 1, x.strip()[:100]))
