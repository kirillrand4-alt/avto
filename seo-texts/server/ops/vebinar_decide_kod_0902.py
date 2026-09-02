# -*- coding: utf-8 -*-
"""Только чтение: что именно делает confirm_decide(status='approved')."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402

исх = inspect.getsource(Store.confirm_decide)
print("строк в методе: %d" % len(исх.splitlines()))
print(исх[:4200])
