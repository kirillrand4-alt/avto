# -*- coding: utf-8 -*-
"""Только чтение: _accepts_now и импорты оркестратора."""
import io
import re

т = io.open(r"C:\sender\sender\orchestrator.py", encoding="utf-8", errors="replace").read()
лн = т.splitlines()
print("=== импорты ===")
for i, л in enumerate(лн[:40]):
    if л.startswith(("import ", "from ")):
        print("  %3d| %s" % (i + 1, л))
н = next(i for i, л in enumerate(лн) if "_accepts_now" in л and "def " in л)
print("\n=== _accepts_now ===")
for i in range(н, min(н + 16, len(лн))):
    print("  %4d| %s" % (i + 1, лн[i]))
print("\n=== есть ли уже наша метка ===")
print("  'закреплённый за письмом' встречается: %d" % т.count("закреплённый за письмом"))
print("  'message=message' в pick_mailbox: %d"
      % len(re.findall(r"pick_mailbox\([^)]*message=", т)))
