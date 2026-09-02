# -*- coding: utf-8 -*-
"""Только чтение: жив ли гейт направлений и как он узнаёт направление письма."""
import inspect
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

карт = getattr(snd, "_cards", None)
print("=== ИНДЕКС ОБЗВОНА (_cards) ===")
print("  объект: %s" % type(карт).__name__)
print("  active: %s" % getattr(карт, "active", "нет атрибута"))
for имя in ("division", "divisions", "size", "__len__"):
    f = getattr(карт, имя, None)
    if f is not None:
        print("  есть %s" % имя)

print("\n=== _napravlenie_pisma ===")
try:
    print(inspect.getsource(S.Sender._napravlenie_pisma)[:1800])
except Exception as ex:
    print("  нет метода: %s" % str(ex)[:100])

print("\n=== ЧТО ОН ВЕРНЁТ НА НАШЕМ ПИСЬМЕ ===")
import sqlite3
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
для = c.execute("SELECT id FROM messages WHERE campaign_id=12 LIMIT 1").fetchone()
msg = store.get_message(для["id"])
try:
    print("  направление письма: %r" % snd._napravlenie_pisma(msg))
except Exception as ex:
    print("  ошибка: %s" % str(ex)[:140])
