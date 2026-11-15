# -*- coding: utf-8 -*-
"""Хвосты логов линз кампании 23 и размер журналов. Только чтение."""
import io, os
for и in ("gaz-linza-23", "gaz-adresat-23"):
    л = r"C:\sender\_ops\%s.log" % и
    if os.path.exists(л): print("==", и, "".join(io.open(л, encoding="utf-8", errors="replace").readlines()[-3:]))
for и in ("gaz-kc-linza-23", "gaz-kc-adresat-23"):
    ж = r"C:\sender\_ops\%s.jsonl" % и
    print(и, sum(1 for _ in io.open(ж, encoding="utf-8")) if os.path.exists(ж) else "нет")
