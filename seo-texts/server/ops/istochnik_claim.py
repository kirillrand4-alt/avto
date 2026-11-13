# -*- coding: utf-8 -*-
"""Исходник серверной версии claim_approved_due и начала tick (сверить с репо). Только чтение."""
import inspect, sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store
from sender.auto_send import AutoSendLoop
print(inspect.getsource(Store.claim_approved_due)[-1800:])
т = inspect.getsource(AutoSendLoop.tick); print(т[т.find("for _ in range"):][:1500])
