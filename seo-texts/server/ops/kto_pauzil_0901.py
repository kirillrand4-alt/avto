# -*- coding: utf-8 -*-
"""Только чтение: состояние ВСЕХ meyer-ящиков и причины пауз. Итог последним."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                 # noqa: E402
import sender.gates as G                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
gates = G.Gates(cfg, store)
snd = S.Sender(cfg, store, Suppression(store), gates)
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ПРИЧИНЫ ПАУЗ (все ящики) ===")
for р in s.execute("SELECT mailbox_id, paused, pause_reason, updated_at, sent_today,"
                   " sent_total FROM mailbox_state WHERE paused=1 ORDER BY updated_at DESC"):
    print("  %-38s сег %3s всего %4s  %s"
          % (str(р["mailbox_id"])[:38], р["sent_today"], р["sent_total"],
             str(р["updated_at"])[:19]))
    print("     причина: %s" % str(р["pause_reason"])[:110])

print("\n=== СТАРЫЕ MEYER-ЯЩИКИ ===")
СТАР = ("optic-sort.ru", "zernosort.ru", "sort-systems.ru")
ост_ст = 0
for mb in cfg.mailboxes():
    if getattr(mb, "division", "") != "meyer":
        continue
    if not any(d in mb.mailbox_id for d in СТАР):
        continue
    r = snd.mailbox_readiness(mb.mailbox_id)
    св = max(0, r.daily_limit - r.sent_today) if r.ready else 0
    ост_ст += св
    print("  %-38s лимит %3d, сегодня %3d, осталось %3d %s"
          % (mb.mailbox_id[:38], r.daily_limit, r.sent_today, св,
             "" if r.ready else "(" + ",".join(r.reasons) + ")"))

print("\n=== ИТОГ ===")
print("  свободная ёмкость СТАРЫХ meyer-ящиков: %d" % ост_ст)
n_p = s.execute("SELECT COUNT(*) n FROM mailbox_state WHERE paused=1").fetchone()["n"]
print("  всего ящиков на паузе: %d из 33" % n_p)
гр = {}
for р in s.execute("SELECT pause_reason, COUNT(*) n FROM mailbox_state"
                   " WHERE paused=1 GROUP BY pause_reason"):
    гр[str(р["pause_reason"])[:60]] = р["n"]
for k, v in гр.items():
    print("     %-62s %d" % (k, v))
