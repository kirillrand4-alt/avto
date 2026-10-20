# -*- coding: utf-8 -*-
"""Почему ящики недоступны для ручной отправки: can_send_now(manual=True) по
каждому ящику и причина (пауза, лимит дня, гейт репутации, окно). Только чтение."""
import inspect
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
snd = getattr(deps.confirm, "_sender", None) or getattr(deps, "live_sender", None) or getattr(deps, "sender", None)
print("отправитель:", type(snd).__name__)
причина_ф = None
for имя in ("why_cannot_send", "block_reason", "_block_reason", "cannot_send_reason"):
    if hasattr(snd, имя):
        причина_ф = getattr(snd, имя)
        print("метод причины:", имя)
now = datetime.now(timezone.utc)
сч = Counter()
for mb in cfg.mailboxes():
    ок = snd.can_send_now(mb.mailbox_id, now=now, manual=True)
    s = store.get_mailbox_state(mb.mailbox_id)
    поля = {k: getattr(s, k, None) for k in ("paused", "pause_reason", "sent_today", "daily_limit", "ramp_day", "day_key",
                                             "gate_tripped", "gate_reason", "cooldown_until")} if s else {}
    сч[(mb.division, ок)] += 1
    if mb.division == "kc" or not ок:
        print("%-45s %-6s можно=%s %s" % (mb.mailbox_id, mb.division, ок, {k: v for k, v in поля.items() if v not in (None, "", 0)}))
print(dict(сч))
try:
    src = inspect.getsource(snd.can_send_now)
    print(src[:2500])
except Exception as е:  # noqa: BLE001
    print("исходник не достать:", е)
