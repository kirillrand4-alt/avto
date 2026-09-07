# -*- coding: utf-8 -*-
"""Только чтение: начало глоссария meyer (хвост уже видели)."""
import io
import json

d = json.load(io.open(r"C:\sender\meyer_glossary.json", encoding="utf-8"))
ключи = list(d.keys())
print("всего терминов: %d" % len(ключи))
for к in ключи[:12]:
    print("\n### %s\n%s" % (к, d[к]))
