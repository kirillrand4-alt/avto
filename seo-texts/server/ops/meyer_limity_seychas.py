# -*- coding: utf-8 -*-
"""Ящики Meyer: ушло сегодня (по day_key), лимит, пауза, последняя отправка. Только чтение."""
import json
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сл = st.get_setting("send_limits") or {}
if isinstance(сл, str):
    сл = json.loads(сл)
пм = сл.get("per_mailbox") or {}
for mb in cfg.mailboxes():
    if mb.division != "meyer":
        continue
    s = st.get_mailbox_state(mb.mailbox_id)
    print("%-38s ушло %3s (день %s) лимит %s пауза %s посл %s" % (mb.mailbox_id, getattr(s, "sent_today", None), getattr(s, "day_key", None),
          пм.get(mb.mailbox_id), getattr(s, "paused", None), str(getattr(s, "last_sent_at", ""))[11:19]))
