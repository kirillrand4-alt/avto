# -*- coding: utf-8 -*-
"""Поставить домен food-sort.ru на паузу по решению владельца.
Обратимо: снимается тем же вызовом с paused=False. argv: проба | делать"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
ПРИЧИНА = "владелец: домен food-sort.ru на паузе"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
цель = [m["mailbox_id"] for m in cfg.get("mailboxes", [])
        if "food-sort.ru" in m["mailbox_id"]]
print("ящики домена: %s" % ", ".join(цель))
for mid in цель:
    s = store.get_mailbox_state(mid)
    print("  %-30s сейчас пауза=%s причина=%s"
          % (mid, getattr(s, "paused", "?"), getattr(s, "pause_reason", None)))

if not ДЕЛАТЬ:
    print("будет поставлено на паузу: %d ящика" % len(цель))
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

for mid in цель:
    store.set_mailbox_paused(mid, True, ПРИЧИНА)
print("\n=== СТАЛО ===")
for mid in цель:
    s = store.get_mailbox_state(mid)
    print("  %-30s пауза=%s причина=%s"
          % (mid, getattr(s, "paused", "?"), getattr(s, "pause_reason", None)))
