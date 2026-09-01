# -*- coding: utf-8 -*-
"""Только чтение: _send_live против штатного пути отправки."""
import io
import re

c = io.open(r"C:\sender\sender\confirm.py", encoding="utf-8",
            errors="replace").read().splitlines()
н = [i for i, x in enumerate(c) if re.match(r"\s*def _send_live", x)]
print("=== confirm.py: _send_live ===")
for i in н:
    for j in range(i, min(i + 80, len(c))):
        print("  %4d  %s" % (j + 1, c[j][:112]))
