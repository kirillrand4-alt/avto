# -*- coding: utf-8 -*-
"""Только чтение: тело прохода tick и размер партии."""
import io
import re

лн = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8",
             errors="replace").read().splitlines()
print("=== __init__ (batch/interval) ===")
н = next(i for i, л in enumerate(лн) if "def __init__" in л)
for i in range(н, min(н + 26, len(лн))):
    print("%4d|%s" % (i + 1, лн[i][:104]))

print("\n=== ТЕЛО ПРОХОДА (после for _ in range(40)) ===")
н2 = next(i for i, л in enumerate(лн) if "for _ in range(40)" in л)
for i in range(н2, min(н2 + 46, len(лн))):
    print("%4d|%s" % (i + 1, лн[i][:104]))
