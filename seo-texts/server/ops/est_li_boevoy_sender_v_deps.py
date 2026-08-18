# -*- coding: utf-8 -*-
"""Есть ли в боевом wiring.py живой sender — тот, без которого цикл не стартует."""
import hashlib
import io

путь = r"C:\sender\sender\wiring.py"
b = io.open(путь, "rb").read()
т = b.decode("utf-8", "replace")
print(f"{путь}: {len(b)} байт sha256={hashlib.sha256(b).hexdigest()}")
for ф in ("live_sender", "confirm.live_send", "live_sender=confirm_sender"):
    print(f"  {ф!r}: {т.count(ф)}")
строки = т.splitlines()
for i, s in enumerate(строки):
    if "live_sender" in s:
        print(f"  {i + 1:>5}| {s[:120]}")
