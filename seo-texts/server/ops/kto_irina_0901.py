# -*- coding: utf-8 -*-
"""Только чтение: имена отправителей meyer-ящиков — есть ли среди них Ирина."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
print("=== MEYER-ЯЩИКИ И ИХ ИМЕНА ===")
for mb in cfg.mailboxes():
    if getattr(mb, "division", "") != "meyer":
        continue
    print("  %-38s %s" % (mb.mailbox_id[:38], mb.from_name or ""))
print("\n=== КЦ-ЯЩИКИ (для полноты) ===")
for mb in cfg.mailboxes():
    if getattr(mb, "division", "") == "meyer":
        continue
    print("  %-38s %s" % (mb.mailbox_id[:38], mb.from_name or ""))
print("\n=== ИТОГ ===")
ир = [mb for mb in cfg.mailboxes() if "ирин" in str(mb.from_name or "").lower()
      or "kuznetsova" in mb.mailbox_id.lower()]
for mb in ир:
    print("  похоже на Ирину: %-38s %s | направление %s"
          % (mb.mailbox_id, mb.from_name, getattr(mb, "division", "?")))
if not ир:
    print("  Ирины среди ящиков нет")
