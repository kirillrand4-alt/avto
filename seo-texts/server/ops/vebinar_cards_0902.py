# -*- coding: utf-8 -*-
"""Только чтение: что такое _cards, почему гейт направлений молчит."""
import inspect
import io
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                   # noqa: E402
import sender.gates as G                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store))
к = getattr(snd, "_cards", None)
print("_cards = %r" % (к,))
print("тип: %s" % type(к))
if к is not None:
    print("атрибуты: %s" % [a for a in dir(к) if not a.startswith("__")][:20])

т = io.open(r"C:\sender\sender\sender.py", encoding="utf-8", errors="replace").read()
лн = т.splitlines()
print("\n=== где задаётся _cards ===")
for м in re.finditer(r"_cards", т):
    н = т[:м.start()].count("\n")
    с = лн[н].strip()
    if "=" in с or "def " in с or "import" in с:
        print("  sender.py:%d  %s" % (н + 1, с[:104]))

print("\n=== настройка индекса обзвона в конфиге ===")
for ключ in ("cards", "obzvon", "cards_index", "division_gate", "napravleniya"):
    зн = cfg.get(ключ, "НЕТ")
    if зн != "НЕТ":
        print("  %s = %s" % (ключ, str(зн)[:200]))
