# -*- coding: utf-8 -*-
"""Разница sender.yaml с бэкапом (секреты маскируем): diff_konfiga.py <бэкап>"""
import difflib
import io
import re
import sys
а = io.open(sys.argv[1], encoding="utf-8").read().splitlines()
б = io.open(r"C:\sender\sender.yaml", encoding="utf-8").read().splitlines()
for л in difflib.unified_diff(а, б, lineterm="", n=0):
    print(re.sub(r"(?i)(pass\w*|token|secret)\s*:\s*\S+", r"\1: ***", л)[:160])
print("=== DIFF ===")
