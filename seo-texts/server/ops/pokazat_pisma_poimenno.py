# -*- coding: utf-8 -*-
"""Показать письма по номерам целиком — чтобы калибровать правило по тексту,
а не по догадке."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ИД = [int(a) for a in sys.argv[1:] if a.isdigit()]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
for rid in ИД:
    row = store.confirm_get(rid) or {}
    тело = row.get("edited_body") or row.get("body") or ""
    print("=" * 70)
    print(f"#{rid}  статус {row.get('status')}  кампания {row.get('campaign_id')}")
    for i, a in enumerate([a for a in тело.split("\n\n") if a.strip()], 1):
        print(f"  [абзац {i}] {a.strip()[:200]}")
