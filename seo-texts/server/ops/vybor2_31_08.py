# -*- coding: utf-8 -*-
"""Только чтение: финал pick_mailbox + где отправка пишет mailbox_state."""
import glob
import io
import os
import re

стр = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
              errors="replace").read().splitlines()
print("=== pick_mailbox, финал выбора (416-470) ===")
for i in range(415, min(472, len(стр))):
    print("  %4d  %s" % (i + 1, стр[i][:112]))

print("\n=== ИТОГ: кто пишет mailbox_state при отправке ===")
for ф in glob.glob(r"C:\sender\sender\*.py"):
    try:
        t = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        continue
    for i, x in enumerate(t):
        if re.search(r"(record_send|bump|note_sent|register_send|upsert_mailbox|"
                     r"set_mailbox_state|mark_sent)", x) and "def " in x:
            print("  %-16s:%-5d %s" % (os.path.basename(ф), i + 1, x.strip()[:92]))
