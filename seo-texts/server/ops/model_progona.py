# -*- coding: utf-8 -*-
"""На какой модели пошёл сегодняшний прогон - строкой из его же лога."""
import glob
import io
import os

п = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-0824-*.log"),
           key=os.path.getmtime, reverse=True)[0]
т = io.open(п, encoding="utf-8", errors="replace").read()
print(f"{os.path.basename(п)}: {len(т)} знаков\n--- первые строки ---")
for с in т.splitlines()[:14]:
    print("  " + с[:160])
print("--- строки про модель ---")
for с in т.splitlines():
    н = с.lower()
    if "модел" in н or "opus" in н or "sonnet" in н or "model" in н:
        print("  " + с[:160])
