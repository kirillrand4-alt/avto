# -*- coding: utf-8 -*-
"""Только чтение: код division_block и блок отправки в оркестраторе."""
import inspect
import io
import sys

sys.path.insert(0, r"C:\sender")
import sender.sender as S  # noqa: E402

print("=== orchestrator.py 520-575 ===")
т = io.open(r"C:\sender\sender\orchestrator.py", encoding="utf-8",
            errors="replace").read().splitlines()
for i in range(519, 576):
    print("  %4d| %s" % (i + 1, т[i][:104]))

print("\n=== division_block ===")
исх = inspect.getsource(S.Sender.division_block)
print(исх[:2600])
