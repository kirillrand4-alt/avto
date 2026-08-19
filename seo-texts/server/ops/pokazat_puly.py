# -*- coding: utf-8 -*-
"""Показать пулы провайдеров и все ящики: кто в пуле, кто мимо."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                       # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
пулы = cfg.provider_pools()
print("== пулы ==")
for имя, спис in пулы.items():
    print(f"\n  {имя} ({len(спис)}):")
    for m in спис:
        print(f"    {m}")

print("\n== ящики конфига, НЕ попавшие ни в один пул ==")
все_в_пулах = {m for спис in пулы.values() for m in спис}
for mb in cfg.mailboxes():
    if mb.mailbox_id not in все_в_пулах:
        div = getattr(mb, "division", "") or "—"
        print(f"  {mb.mailbox_id:<38} провайдер={mb.provider:<8} направление={div}")
