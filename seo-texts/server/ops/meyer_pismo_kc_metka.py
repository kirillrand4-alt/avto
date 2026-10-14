# -*- coding: utf-8 -*-
"""Письма Meyer в очереди подтверждения, у которых компания в базе обзвона
помечена без meyer: ящик не подберётся (письмо Meyer шлём только с Meyer, а
компании разрешены только ящики её метки). Только счёт, ничего не меняет."""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
cards = cs._cards
g = getattr(cards, "divisions", None)
with store._lock:
    ids = [r[0] for r in store._conn.execute("SELECT id FROM confirm_reviews WHERE status='pending'")]
итог, метки, прим = Counter(), Counter(), []
for i in ids:
    с = cs.get(i)
    лд = cs.letter_division(с)
    if not str(лд or "").startswith("meyer"):
        continue
    итог["meyer писем"] += 1
    раз = g(с.get("inn")) if callable(g) else None
    if раз is None:
        итог["нет в базе обзвона"] += 1
        continue
    if not any(str(x).startswith("meyer") for x in раз):
        итог["метка без meyer -> ящика нет"] += 1
        метки["+".join(sorted(раз))] += 1
        if len(прим) < 12:
            прим.append("#%d %s %s" % (i, с.get("email"), (с.get("company") or с.get("company_name") or "")[:40]))
print(dict(итог))
print("метки у застрявших:", dict(метки))
for п in прим:
    print("  ", п)
print("=== MEYER-ПИСЬМА С МЕТКОЙ КЦ ===")
