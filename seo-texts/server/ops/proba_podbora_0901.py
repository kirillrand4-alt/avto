# -*- coding: utf-8 -*-
"""Только чтение: боевой подбор ящика для остатка очереди."""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                 # noqa: E402
import sender.gates as G                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

ряды = list(s.execute(
    "SELECT m.id, m.campaign_id, m.recipient_id FROM messages m"
    " WHERE m.status='scheduled' AND m.scheduled_at <= ?"
    " AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id"
    "      ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')"
    " ORDER BY m.scheduled_at LIMIT 25", (now_iso,)))
print("=== ПРОБА ПОДБОРА НА %d ПИСЬМАХ ===" % len(ряды))
c = Counter()
примеры = []
for р in ряды:
    rec = store.get_recipient(р["recipient_id"])
    camp = store.get_campaign(р["campaign_id"])
    msg = store.get_message(р["id"])
    if not rec or not camp:
        c["нет получателя/кампании"] += 1
        continue
    try:
        mid = snd.pick_mailbox(rec, camp, message=msg)
    except Exception as ex:
        c["ОШИБКА: %s" % str(ex)[:50]] += 1
        continue
    if mid:
        c["ящик найден: %s" % mid] += 1
    else:
        c["ЯЩИК НЕ НАЙДЕН"] += 1
        if len(примеры) < 4:
            примеры.append((р["id"], getattr(rec, "email", ""),
                            getattr(rec, "inn", "")))
for k, v in c.most_common():
    print("  %-52s %d" % (k[:52], v))
for i, e, inn in примеры:
    print("     без ящика: msg#%s %s инн %s" % (i, e, inn))

print("\n=== ОКНО ДЛЯ КОНКРЕТНОГО ПИСЬМА ===")
if ряды:
    рец = store.get_recipient(ряды[0]["recipient_id"])
    try:
        print("  _within_window сейчас: %s"
              % snd._within_window(datetime.now().astimezone()))
    except Exception as ex:
        print("  окно: %s" % str(ex)[:70])
    print("  tz получателя: %r, регион %r"
          % (getattr(рец, "tz", None), getattr(рец, "region", None)))

print("\n=== ИТОГ ===")
print("  сейчас мск %s" % datetime.now().strftime("%H:%M:%S"))
print("  если ящик находится у всех — значит тик оркестратора не идёт")
