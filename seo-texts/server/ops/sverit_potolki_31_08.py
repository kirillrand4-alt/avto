# -*- coding: utf-8 -*-
"""Только чтение: текущие ручные потолки и не потерялся ли a.kozlov."""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
v = store.get_setting("send_limits")
if isinstance(v, str) and v:
    v = json.loads(v)
per = (v or {}).get("per_mailbox") or {}
print("=== send_limits ===")
print("  all = %r, записей per_mailbox = %d" % ((v or {}).get("all"), len(per)))
print("\n  все значения:")
for k in sorted(per):
    print("     %-42s %s" % (k[:42], per[k]))
print("\n=== ИТОГ ===")
print("  a.kozlov@zernosort.ru в потолках: %r" % per.get("a.kozlov@zernosort.ru", "НЕТ"))
print("  food-sort ящики: %r" % {k: v2 for k, v2 in per.items() if "food-sort" in k})
