# -*- coding: utf-8 -*-
"""Ход разметки провалов Meyer (только чтение)."""
import io, json, os
from collections import Counter
print("".join(io.open(r"C:\sender\_ops\meyer-provaly-klass.log", encoding="utf-8", errors="replace").readlines()[-6:]))
ж = r"C:\sender\_ops\meyer-provaly-klass.jsonl"
if os.path.exists(ж): print("размечено:", sum(1 for _ in io.open(ж, encoding="utf-8")), dict(Counter(json.loads(с)["shablon"] for с in io.open(ж, encoding="utf-8"))))
