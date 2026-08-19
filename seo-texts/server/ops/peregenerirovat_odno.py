# -*- coding: utf-8 -*-
"""Перегенерировать ОДНО письмо очереди по номеру.

Нужно, когда владелец показал конкретное письмо: групповые прогоны берут
что попадётся, а починить надо именно это.

    python zapusk_svoego_skripta.py ops/peregenerirovat_odno.py 1240
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

RID = int(next((a for a in sys.argv[1:] if a.isdigit()), "0"))
if not RID:
    print("укажи номер письма")
    raise SystemExit(2)

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

было = store.confirm_get(RID) or {}
print(f"#{RID} было:\n{(было.get('body') or '')[:600]}\n" + "-" * 68)
res = q.regenerate_review(RID)
print("итог:", {k: v for k, v in res.items() if k != "subject"})
стало = store.confirm_get(RID) or {}
print(f"\n#{RID} стало:\nТЕМА: {стало.get('subject')}\n\n"
      f"{(стало.get('body') or '')[:1400]}")
