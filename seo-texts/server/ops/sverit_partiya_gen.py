# -*- coding: utf-8 -*-
"""Чем отличаются три копии partiya_gen: _ops (боевая), server\\ops, и что в ней есть."""
import hashlib
import io
import os

пути = {"_ops (её и запускаем)": r"C:\sender\_ops\partiya_gen.py",
        "server\\ops (куда кладёт dep)": r"C:\sender\server\ops\partiya_gen.py"}
тексты = {}
for имя, п in пути.items():
    т = io.open(п, encoding="utf-8", errors="replace").read()
    тексты[имя] = т
    print("%-30s %7d знаков  sha %s" % (имя, len(т),
                                        hashlib.sha1(т.encode()).hexdigest()[:12]))
a, b = list(тексты.values())
if a == b:
    print("\nкопии совпадают")
else:
    сa = a.splitlines()
    сb = b.splitlines()
    только_a = [с for с in сa if с not in set(сb)]
    только_b = [с for с in сb if с not in set(сa)]
    print("\nстрок только в _ops: %d, только в server\\ops: %d"
          % (len(только_a), len(только_b)))
    print("--- только в _ops ---")
    for с in только_a[:25]:
        print("   " + с[:150])
    print("--- только в server\\ops ---")
    for с in только_b[:25]:
        print("   " + с[:150])
