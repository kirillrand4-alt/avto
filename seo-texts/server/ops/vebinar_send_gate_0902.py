# -*- coding: utf-8 -*-
"""Только чтение: с какими аргументами send() зовёт division_block."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
import sender.sender as S  # noqa: E402

исх = inspect.getsource(S.Sender.send).splitlines()
н = next(i for i, л in enumerate(исх) if "division_block(" in л)
print("=== send(), окрестность проверки направления ===")
for i in range(max(0, н - 12), min(len(исх), н + 16)):
    print("  %s" % исх[i][:104])
