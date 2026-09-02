# -*- coding: utf-8 -*-
"""Только чтение: что делает цикл с письмом без региона и часовой зоны."""
import datetime as dt
import inspect
import io
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
import sender.auto_send as A      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("=== recipient_tz_name ===")
print(inspect.getsource(A.recipient_tz_name)[:900])

лн = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8",
             errors="replace").read().splitlines()
н = next(i for i, л in enumerate(лн) if "def _send_one" in л)
print("\n=== _send_one: окно ===")
for i in range(н, min(н + 34, len(лн))):
    print("%4d|%s" % (i + 1, лн[i][:104]))

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
р = c.execute("SELECT recipient_id FROM messages WHERE campaign_id=12 LIMIT 1").fetchone()
rec = store.get_recipient(р["recipient_id"])
win = A.window_from(store, cfg)
print("\n=== НА НАШЕМ ПОЛУЧАТЕЛЕ ===")
print("  email=%s region=%r tz=%r" % (rec.email, rec.region, rec.tz))
try:
    зона = A.recipient_tz_name(cfg, rec)
    print("  зона: %r" % зона)
    слот = A.next_slot(dt.datetime.now(dt.timezone.utc), win, зона)
    print("  next_slot: %s" % слот)
except Exception as ex:
    print("  ошибка: %s: %s" % (type(ex).__name__, str(ex)[:140]))
