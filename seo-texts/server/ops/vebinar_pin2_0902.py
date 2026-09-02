# -*- coding: utf-8 -*-
"""Только чтение: подтверждение переносит НАШ текст в письмо или нет."""
import inspect
import io
import sys

sys.path.insert(0, r"C:\sender")
from sender import store as S  # noqa: E402

print("=== confirm_submit: сигнатура ===")
print("  " + str(inspect.signature(S.Store.confirm_submit)))

т = io.open(r"C:\sender\sender\store.py", encoding="utf-8", errors="replace").read().splitlines()
print("\n=== store.py 1856-1900 (перенос текста в message) ===")
for i in range(1855, 1900):
    print("  %4d| %s" % (i + 1, т[i][:110]))
