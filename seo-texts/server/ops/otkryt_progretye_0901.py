# -*- coding: utf-8 -*-
"""Снять паузу с ПРОГРЕТЫХ meyer-ящиков, новые оставить на паузе.

Прогретые - на доменах optic-sort.ru, zernosort.ru, sort-systems.ru: за сегодня
у них ноль спам-отказов. Новые шесть доменов остаются на паузе: три отказа из
пяти пришли с food-sort.ru, ещё два сегодня с rentgen-control и
rentgen-inspection. Без primenit ничего не меняет."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                 # noqa: E402
import sender.gates as G                  # noqa: E402

ПРИМЕНИТЬ = "primenit" in sys.argv
ПРОГРЕТЫЕ = ("optic-sort.ru", "zernosort.ru", "sort-systems.ru")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

цель = []
for mb in cfg.mailboxes():
    if getattr(mb, "division", "") != "meyer":
        continue
    if not any(d in mb.mailbox_id for d in ПРОГРЕТЫЕ):
        continue
    от = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='reject_spam'"
                   " AND mailbox_id=? AND created_at >= date('now')",
                   (mb.mailbox_id,)).fetchone()["n"]
    цель.append((mb.mailbox_id, от))

print("=== ПРОГРЕТЫЕ MEYER: спам-отказов сегодня ===")
for m, от in цель:
    р = s.execute("SELECT paused FROM mailbox_state WHERE mailbox_id=?", (m,)).fetchone()
    print("  %-38s отказов %d, paused=%s" % (m[:38], от, р["paused"] if р else "?"))

грязные = [m for m, от in цель if от > 0]
чистые = [m for m, от in цель if от == 0]
print("\n  снимаю паузу у чистых: %d" % len(чистые))
print("  оставляю с отказами   : %s" % (грязные or "нет"))

if ПРИМЕНИТЬ:
    for m in чистые:
        store.set_mailbox_paused(m, False, None)
    print("\n  ПРИМЕНЕНО: снята пауза с %d ящиков" % len(чистые))

print("\n=== ИТОГ: ГОТОВНОСТЬ ПОСЛЕ ===")
ост = 0
for mb in cfg.mailboxes():
    if getattr(mb, "division", "") != "meyer":
        continue
    r = snd.mailbox_readiness(mb.mailbox_id)
    св = max(0, r.daily_limit - r.sent_today) if r.ready else 0
    ост += св
    if r.ready or any(d in mb.mailbox_id for d in ПРОГРЕТЫЕ):
        print("  %-38s лимит %3d, сегодня %3d, свободно %3d %s"
              % (mb.mailbox_id[:38], r.daily_limit, r.sent_today, св,
                 "ГОТОВ" if r.ready else "(" + ",".join(r.reasons) + ")"))
print("  свободная ёмкость meyer: %d" % ост)
n = s.execute("SELECT COUNT(*) n FROM mailbox_state WHERE paused=1").fetchone()["n"]
print("  ящиков на паузе: %d из 33" % n)
print("  РЕЖИМ: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "показ без изменений"))
