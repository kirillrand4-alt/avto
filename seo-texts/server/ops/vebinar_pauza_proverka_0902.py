# -*- coding: utf-8 -*-
"""Только чтение: сверяем паузу по прямому SQL и по объекту Store."""
import dataclasses
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== ПРЯМОЙ SQL ===")
for р in c.execute("SELECT mailbox_id, paused, pause_reason, day_key, sent_today"
                   " FROM mailbox_state WHERE mailbox_id LIKE '%food-sort%'"
                   " OR paused=1"):
    print("  %-34s paused=%s причина=%s" % (р["mailbox_id"], р["paused"],
                                            р["pause_reason"]))

s = store.get_mailbox_state("a.erokhin@food-sort.ru")
print("\n=== ОБЪЕКТ MailboxState ===")
if dataclasses.is_dataclass(s):
    for f in dataclasses.fields(s):
        print("  %-16s = %r" % (f.name, getattr(s, f.name)))
else:
    print("  не dataclass: %r" % (s,))
