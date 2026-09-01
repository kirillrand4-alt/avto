# -*- coding: utf-8 -*-
"""Только чтение: середина pick_mailbox и _last_sent_mailbox."""
import io
import re

стр = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
              errors="replace").read().splitlines()
н = None
for i, x in enumerate(стр):
    if re.match(r"\s*def _last_sent_mailbox", x):
        н = i
        break
print("=== _last_sent_mailbox ===")
if н is not None:
    for i in range(н, min(н + 24, len(стр))):
        print("  %4d  %s" % (i + 1, стр[i][:110]))

print("\n=== ИТОГ: pick_mailbox, строки 416-446 ===")
for i in range(415, 446):
    print("  %4d  %s" % (i + 1, стр[i][:112]))
