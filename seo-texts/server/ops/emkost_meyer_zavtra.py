# -*- coding: utf-8 -*-
"""Ёмкость мейеровских ящиков ЗАВТРА и хватит ли на неё писем.

Рамп-день у каждого ящика завтра на единицу больше, лимит берём той же
кривой, какой его берёт сам отправщик, — не на глаз.
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards                           # noqa: E402
from sender.config import Config                                       # noqa: E402
from sender.gates import Gates                                         # noqa: E402
from sender.sender import Sender                                       # noqa: E402
from sender.store import Store                                         # noqa: E402
from sender.suppression import Suppression                             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True,
             cards=CompanyCards(
                 index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                 enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "")
                 or None))
now = datetime.now(timezone.utc)

итог = {"Meyer": [0, 0], "КЦ": [0, 0]}       # [сегодня осталось, завтра всего]
print("== ящики: сегодня осталось / завтра потолок ==")
for mb in cfg.mailboxes():
    div = str(getattr(mb, "division", "") or "").lower()
    напр = "Meyer" if ("meyer" in div or "мейер" in div) else "КЦ"
    st = store.get_mailbox_state(mb.mailbox_id)
    сег = getattr(st, "sent_today", 0) if st else 0
    рд = getattr(st, "ramp_day", 0) if st else 0
    лим_сег = snd._daily_limit(mb.provider, рд, mb.mailbox_id)
    лим_зав = snd._daily_limit(mb.provider, рд + 1, mb.mailbox_id)
    итог[напр][0] += max(0, лим_сег - сег)
    итог[напр][1] += лим_зав
    if напр == "Meyer":
        print(f"  {mb.mailbox_id:<38} рамп{рд:>3}->{рд+1:<3} "
              f"сегодня {сег}/{лим_сег} (осталось {max(0, лим_сег - сег)})  "
              f"завтра потолок {лим_зав}")

print(f"\n  Meyer: сегодня осталось {итог['Meyer'][0]}, "
      f"завтра потолок {итог['Meyer'][1]}")
print(f"  КЦ:    сегодня осталось {итог['КЦ'][0]}, "
      f"завтра потолок {итог['КЦ'][1]}")

print("\n== чем это закрывать ==")
for камп, имя in ((11, "Meyer"), (10, "КЦ")):
    with store._lock:
        одобр = store._conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
            "ON c.message_id=m.id WHERE c.campaign_id=? "
            "AND m.status='scheduled' AND (SELECT cr.status FROM "
            "confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC "
            "LIMIT 1) IN ('approved','edited')", (камп,)).fetchone()[0]
        ждут_реш = store._conn.execute(
            "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=? "
            "AND status='pending'", (камп,)).fetchone()[0]
    зав = итог[имя][1]
    print(f"  {имя:<6} одобрено и ждёт {одобр:>4} | без решения {ждут_реш:>4} "
          f"| завтрашний потолок {зав:>3} -> "
          + ("ХВАТАЕТ" if одобр >= зав else f"НЕ ХВАТАЕТ, нужно ещё {зав - одобр}"))
