# -*- coding: utf-8 -*-
"""Тот же разбор, но БОЕВЫМ сендером — тем самым, каким пользуется цикл.

Прошлый разбор я делал через deps.sender (dry_run=True), а автоотправка
работает через deps.live_sender (dry_run=False). Это разные объекты, и
проверять надо тот, который реально решает. Ничего не отправляем: зовём
только pick_mailbox и can_send_now.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (recipient_tz_name, window_from,      # noqa: E402
                              within_window_now)
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
from sender.wiring import build_deps                               # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
сухой, боевой = deps.sender, deps.live_sender
сейчас = datetime.now(timezone.utc)
win = window_from(store, cfg)
print(f"сейчас {сейчас.strftime('%H:%M')} UTC, окно {win}")
print(f"сухой dry_run={сухой.dry_run}, боевой dry_run={боевой.dry_run}\n")

print("can_send_now по ящикам (сухой -> боевой):")
for mb in cfg.mailboxes():
    с = сухой.can_send_now(mb.mailbox_id, now=сейчас)
    б = боевой.can_send_now(mb.mailbox_id, now=сейчас)
    if с != б or с:
        print(f"  {mb.mailbox_id:<40} сухой={с} боевой={б}")

with store._lock:
    ряд = store._conn.execute(
        """SELECT m.id, m.recipient_id, m.campaign_id FROM messages m
            WHERE m.status='scheduled' AND m.scheduled_at <= ?
              AND (SELECT cr.status FROM confirm_reviews cr
                    WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1)
                  IN ('approved','edited')
            ORDER BY m.scheduled_at LIMIT 60""",
        (сейчас.isoformat(),)).fetchall()

свод = Counter()
for mid, rid, cid in ряд:
    r = store.get_recipient(int(rid))
    камп = store.get_campaign(int(cid))
    if r is None or камп is None:
        свод["нет получателя/кампании"] += 1
        continue
    tz = recipient_tz_name(win, r)
    if not within_window_now(win, tz, сейчас):
        свод[f"вне окна ({tz})"] += 1
        continue

    class _M:
        id = mid
    я_с = сухой.pick_mailbox(r, камп, now=сейчас, message=_M())
    я_б = боевой.pick_mailbox(r, камп, now=сейчас, message=_M())
    свод[f"сухой={я_с or '-'} | боевой={я_б or '-'}"] += 1

print(f"\nписем разобрано: {len(ряд)}")
for к, n in свод.most_common(12):
    print(f"  {n:>4}  {к}")
