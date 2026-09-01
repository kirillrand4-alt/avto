# -*- coding: utf-8 -*-
"""Только чтение: чем заканчивается _send_live (993-1075)."""
import io

c = io.open(r"C:\sender\sender\confirm.py", encoding="utf-8",
            errors="replace").read().splitlines()
for j in range(992, min(1078, len(c))):
    print("  %4d  %s" % (j + 1, c[j][:112]))
