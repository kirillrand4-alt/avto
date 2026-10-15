# -*- coding: utf-8 -*-
"""Лимиты ящиков КЦ: провайдер, рамп-день, кривая, ручной потолок send_limits."""
import json
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.ramp import daily_send_limit  # noqa: E402
from sender.store import Store  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
print("send_limits:", str(st.get_setting("send_limits"))[:400])
пров = Counter()
for mb in cfg.mailboxes():
    if mb.division != "kc":
        continue
    s = st.get_mailbox_state(mb.mailbox_id)
    рд = getattr(s, "ramp_day", 0) if s else 0
    пров[mb.provider] += 1
    print("%-45s %-10s рамп %3s база %3s ушло %s пауза %s" % (mb.mailbox_id, mb.provider, рд,
          daily_send_limit(cfg, mb.provider, рд), getattr(s, "sent_today", 0) if s else 0, getattr(s, "paused", None) if s else None))
for p in пров:
    print("кривая %s: %s" % (p, cfg.ramp_curve(p)))
print("=== ЛИМИТЫ КЦ ===")
