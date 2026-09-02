# -*- coding: utf-8 -*-
"""Только чтение: полный код claim_approved_due."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store  # noqa: E402

print(inspect.getsource(Store.claim_approved_due)[:3400])
