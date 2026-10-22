# -*- coding: utf-8 -*-
"""Паузы ящиков: кто на паузе, причина и когда; отказы по спаму (5.7.1/SPAM)
за сутки по направлениям и по ящикам. Только чтение."""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
нап = {mb.mailbox_id: mb.division for mb in cfg.mailboxes()}
сч = Counter()
for mb, d in нап.items():
    s = st.get_mailbox_state(mb)
    п = bool(getattr(s, "paused", False)) if s else False
    сч[(d, п)] += 1
    if п:
        print("ПАУЗА %-42s %-6s причина=%s с=%s" % (mb, d, getattr(s, "pause_reason", None),
                                                    getattr(s, "paused_at", None) or getattr(s, "updated_at", None)))
print("итог (направление, пауза):", dict(сч))
c = sqlite3.connect(r"C:\sender\sender.db")
сп = Counter()
for mb, ts in c.execute("SELECT m.mailbox_id, e.event_ts FROM events e JOIN messages m ON m.id=e.message_id "
                        "WHERE e.event_type IN ('reject_spam') AND e.event_ts>=strftime('%Y-%m-%dT%H:%M:%S','now','-1 day')"):
    сп[нап.get(mb, "?")] += 1
print("reject_spam за сутки по направлениям:", dict(сп))
for r in c.execute("SELECT e.event_ts, m.mailbox_id FROM events e JOIN messages m ON m.id=e.message_id WHERE e.event_type='reject_spam' "
                   "ORDER BY e.id DESC LIMIT 25"):
    print("   ", r[0][:19], r[1])
