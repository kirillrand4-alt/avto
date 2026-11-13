# -*- coding: utf-8 -*-
"""Почему автоотправка не берёт созревшие письма: для 5 созревших писем КЦ — pick_mailbox (сухой Sender) и по каждому
ящику пула: division_block / can_send_now. Ничего не отправляет. Только чтение."""
import sqlite3, sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.wiring import build_deps
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(r"C:\sender\sender.db")
d = build_deps(cfg, st, dry_run=True); s = d.sender
now = datetime.now(timezone.utc)
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
ids = [r[0] for r in c.execute("SELECT id FROM messages WHERE status='scheduled' AND scheduled_at<=? AND campaign_id=22 ORDER BY scheduled_at LIMIT 5", (now.strftime('%Y-%m-%dT%H:%M:%S'),))]
print("письма:", ids, "| окно сендера:", s._within_window(now))
for mid in ids[:3]:
    m = st.get_message(mid) if hasattr(st, "get_message") else None
    rec = st.get_recipient(m.recipient_id); camp = st.get_campaign(m.campaign_id)
    print("\n#%s кампания %s ящик-в-письме %s -> pick: %s" % (mid, m.campaign_id, m.mailbox_id, s.pick_mailbox(rec, camp, now=now, message=m)))
    print("   ящик письма:", m.mailbox_id, "can:", s.can_send_now(m.mailbox_id, now=now) if m.mailbox_id else "-", "div:", s.division_block(rec, m.mailbox_id, message=m) if m.mailbox_id else "-")
    for mb in []:
        db = s.division_block(rec, mb.mailbox_id, message=m)
        print("   %-44s div:%s can:%s" % (mb.mailbox_id, db, s.can_send_now(mb.mailbox_id, now=now)))
