# -*- coding: utf-8 -*-
"""Только чтение: какой объект нужен ProbeSync."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                # noqa: E402
from sender.store import Store                  # noqa: E402
from sender.addr_probe import build_addr_probe  # noqa: E402
import sender.probe_sync as PS                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
print("\n=== build_probe_sync ===")
print(inspect.getsource(PS.build_probe_sync)[:900])
print("\n=== ProbeSync.срочно ===")
print(inspect.getsource(PS.ProbeSync.срочно)[:1400])

петля = build_addr_probe(store, cfg)
print("build_addr_probe вернул: %s" % type(петля).__name__)
print("  его атрибуты: %s" % [a for a in dir(петля) if not a.startswith("_")][:22])
для = getattr(петля, "probe", None)
print("  .probe это: %s" % type(для).__name__)
for имя in dir(петля):
    if имя.startswith("_"):
        continue
    о = getattr(петля, имя)
    if hasattr(о, "cached"):
        print("  ОБЪЕКТ С cached: петля.%s -> %s" % (имя, type(о).__name__))

