# -*- coding: utf-8 -*-
"""Глобальный гейт и гейты ящиков КЦ (только статус, кратко). Только чтение."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.gates import Gates
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db"); g = Gates(cfg, st)
print("глобальный:", g.check_global())
закр = [(m.mailbox_id, g.check_mailbox(m.mailbox_id)) for m in cfg.mailboxes()]
print("закрытых ящиков:", [(a, str(b)[:120]) for a, b in закр if b.tripped])
print("пулы КЦ:", {m.mailbox_id: m.pool for m in cfg.mailboxes() if m.division == "kc"} and sorted({m.pool for m in cfg.mailboxes() if m.division == "kc"}))
