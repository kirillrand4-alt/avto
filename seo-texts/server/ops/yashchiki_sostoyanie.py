# -*- coding: utf-8 -*-
"""Состояние ящиков: пауза, лимит, сколько ушло сегодня, что говорит can_send_now.

send_as перестал подбирать ящик всем 47 письмам - значит пригодных не
осталось. Причина всегда одна из трёх: пауза, дневной лимит или гейт.
Показываем всё разом, по каждому ящику.
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
s = deps.sender
сейчас = datetime.now(timezone.utc)
print(f"сейчас UTC {сейчас:%Y-%m-%d %H:%M}\n")
print(f"{'ящик':<44} {'напр':<6} {'пауза':<6} {'ушло':>5}/{'лимит':<6} "
      f"{'можно сейчас'}")
for mb in cfg.mailboxes():
    ст = store.get_mailbox_state(mb.mailbox_id)
    ушло = getattr(ст, "sent_today", 0) if ст else 0
    лимит = getattr(ст, "daily_limit", 0) if ст else 0
    пауза = getattr(ст, "paused", False) if ст else False
    день = getattr(ст, "day_key", "") if ст else ""
    try:
        можно = s.can_send_now(mb.mailbox_id, now=сейчас, manual=True)
    except Exception as ex:                                       # noqa: BLE001
        можно = f"ошибка: {str(ex)[:40]}"
    print(f"{mb.mailbox_id:<44} {str(mb.division or '-'):<6} "
          f"{'ДА' if пауза else 'нет':<6} {ушло:>5}/{лимит:<6} {можно}  {день}")
