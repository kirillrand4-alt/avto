# -*- coding: utf-8 -*-
"""Только чтение: логика рампы/лимита и точное состояние ящиков."""
import io
import sqlite3

print("=== sender.py: как считается ramp/лимит (1240-1300) ===")
стр = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
              errors="replace").read().splitlines()
for i in range(1238, 1300):
    if i < len(стр):
        print("  %4d  %s" % (i + 1, стр[i][:112]))
