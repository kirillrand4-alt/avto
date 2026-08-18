# -*- coding: utf-8 -*-
"""Полная трассировка сбоя из panel_err.log: кто именно упал и когда."""
import io
import os
import re

путь = r"C:\sender\_ops\panel_err.log"
р = os.path.getsize(путь)
with io.open(путь, "rb") as f:
    f.seek(max(0, р - 300_000))
    текст = f.read().decode("utf-8", "replace")
блоки = текст.split("Traceback (most recent call last)")
print(f"файл {р} байт, трассировок в хвосте: {len(блоки) - 1}\n")
for б in блоки[-3:]:
    print("=" * 70)
    print("Traceback (most recent call last)" + б[:2600])
