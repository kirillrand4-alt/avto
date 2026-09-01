# -*- coding: utf-8 -*-
"""Только чтение: как выбирается ящик для письма."""
import glob
import io
import os
import re

файлы = glob.glob(r"C:\sender\sender\*.py")
print("=== ФУНКЦИИ ВЫБОРА ЯЩИКА ===")
кандидаты = []
for ф in файлы:
    try:
        стр = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        continue
    for i, x in enumerate(стр):
        if re.match(r"\s*def .*(pick|choose|select|vybr|next).*mailbox", x, re.I) or \
           re.match(r"\s*def .*mailbox.*(pick|choose|select|for)", x, re.I):
            кандидаты.append((ф, i, x.strip()))
            print("  %-18s:%-5d %s" % (os.path.basename(ф), i + 1, x.strip()[:80]))

for ф, i, _ in кандидаты[:3]:
    стр = io.open(ф, encoding="utf-8", errors="replace").read().splitlines()
    print("\n=== %s:%d ===" % (os.path.basename(ф), i + 1))
    for j in range(i, min(i + 46, len(стр))):
        print("  %4d  %s" % (j + 1, стр[j][:112]))
