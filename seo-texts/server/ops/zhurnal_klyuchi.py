# -*- coding: utf-8 -*-
"""Ключи записей брака журнала: zhurnal_klyuchi.py <журнал>. Только чтение."""
import io, json, sys
from collections import Counter
сч = Counter()
for l in io.open(sys.argv[1], encoding="utf-8"):
    try: z = json.loads(l)
    except ValueError: continue
    if not z.get("ок") and z.get("inn"):
        сч[tuple(sorted(k for k in z if z.get(k)))] += 1
for k, n in сч.most_common(4): print(n, k)
