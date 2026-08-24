# -*- coding: utf-8 -*-
"""Куски боевого imap_watcher.py: как получают signal и как строят тег."""
import io
т = io.open(r"C:\sender\sender\imap_watcher.py", encoding="utf-8").read().split("\n")
for a, b, имя in ((404, 448, "получение signal"), (596, 626, "построение тега")):
    print("=== %s (%d-%d) ===" % (имя, a, b))
    for н in range(a - 1, min(b, len(т))):
        print("%-5d %s" % (н + 1, т[н]))
    print()
