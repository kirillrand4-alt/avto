# -*- coding: utf-8 -*-
"""Три ящика Meyer на паузе: какие и почему."""
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.gates import Gates                                  # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
gates = Gates(cfg, store)
теперь = datetime.now(timezone.utc)
for mb in cfg.mailboxes():
    if str(getattr(mb, "division", "")).lower() != "meyer":
        continue
    st = store.get_mailbox_state(mb.mailbox_id)
    гм = gates.check_mailbox(mb.mailbox_id)
    пауза = bool(st is not None and getattr(st, "paused", False))
    if not пауза and not getattr(гм, "tripped", False):
        continue
    print("   %-36s пауза=%s гейт=%s %s"
          % (mb.mailbox_id[:36], пауза, getattr(гм, "tripped", "?"),
             str(getattr(гм, "reason", "") or getattr(st, "pause_reason", ""))[:70]))
    if st is not None:
        for поле in ("pause_reason", "paused_at", "sent_today", "day_key",
                     "daily_limit"):
            з = getattr(st, поле, None)
            if з not in (None, ""):
                print("      %-14s %s" % (поле, з))
print("")
print("=" * 70)
print("=== ЯЩИКИ MEYER НА ПАУЗЕ ===")
