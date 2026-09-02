# -*- coding: utf-8 -*-
"""Только чтение: точный кусок оркестратора вокруг выбора ящика."""
import io

т = io.open(r"C:\sender\sender\orchestrator.py", encoding="utf-8",
            errors="replace").read().splitlines()
for i in range(514, 556):
    print("%4d|%s" % (i + 1, т[i]))
