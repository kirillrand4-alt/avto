# -*- coding: utf-8 -*-
"""Только чтение: start() цикла и как его собирают в панели."""
import io

лн = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8",
             errors="replace").read().splitlines()
н = next(i for i, л in enumerate(лн) if "def start" in л)
print("=== auto_send.py: start() и рядом ===")
for i in range(max(0, н - 6), min(н + 34, len(лн))):
    print("%4d|%s" % (i + 1, лн[i][:104]))

лн2 = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8",
              errors="replace").read().splitlines()
print("\n=== app.py: сборка цикла ===")
for i in range(1602, 1622):
    print("%4d|%s" % (i + 1, лн2[i][:104]))
