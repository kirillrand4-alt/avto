# -*- coding: utf-8 -*-
"""Только чтение: уйдут ли корректно письма, запланированные на сегодня."""
import sqlite3
import sys
from collections import Counter
from datetime import datetime

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

print("=== ЗАПЛАНИРОВАНО: РАЗБИВКА ===")
for р in s.execute("SELECT campaign_id k, COUNT(*) n,"
                   " SUM(CASE WHEN scheduled_at <= datetime('now','+1 day') THEN 1 ELSE 0 END) сег,"
                   " MIN(scheduled_at) s1, MAX(scheduled_at) s2"
                   " FROM messages WHERE status='scheduled' GROUP BY k"):
    print("  кампания %-3s всего %4d | в ближайшие сутки %4d | %s .. %s"
          % (р["k"], р["n"], р["сег"], str(р["s1"])[:16], str(р["s2"])[:16]))

print("\n=== ПРИВЯЗКА К ЯЩИКУ ===")
c = Counter()
for р in s.execute("SELECT COALESCE(mailbox_id,'(не назначен)') m, COUNT(*) n"
                   " FROM messages WHERE status='scheduled' GROUP BY m ORDER BY n DESC"):
    c[р["m"]] = р["n"]
    print("  %-42s %5d" % (str(р["m"])[:42], р["n"]))

print("\n=== ЁМКОСТЬ ПО НАПРАВЛЕНИЯМ (готовые ящики) ===")
ём = Counter()
готовых = Counter()
for mb in cfg.mailboxes():
    r = snd.mailbox_readiness(mb.mailbox_id)
    d = getattr(mb, "division", "?")
    if r.ready:
        ём[d] += max(0, r.daily_limit - r.sent_today)
        готовых[d] += 1
for d in sorted(ём):
    print("  %-8s готовых ящиков %2d, свободная ёмкость сегодня %4d" % (d, готовых[d], ём[d]))

print("\n=== СКОЛЬКО ПИСЕМ НА КАЖДОЕ НАПРАВЛЕНИЕ ===")
нужно = Counter()
for р in s.execute("SELECT campaign_id, COUNT(*) n FROM messages"
                   " WHERE status='scheduled' GROUP BY campaign_id"):
    нужно["kc" if р["campaign_id"] == 10 else "meyer" if р["campaign_id"] == 11
          else str(р["campaign_id"])] += р["n"]
for k, v in нужно.items():
    print("  %-8s писем %4d | ёмкость %4d | %s"
          % (k, v, ём.get(k, 0), "ХВАТАЕТ" if ём.get(k, 0) >= v else "НЕ ХВАТАЕТ на сегодня"))

print("\n=== ПРОБА БОЕВЫМ ПОДБОРОМ: 40 писем из очереди ===")
проб = list(s.execute("SELECT id, campaign_id, recipient_id FROM messages"
                      " WHERE status='scheduled' ORDER BY scheduled_at LIMIT 40"))
итог = Counter()
примеры = []
for р in проб:
    rec = store.get_recipient(р["recipient_id"])
    camp = store.get_campaign(р["campaign_id"])
    msg = store.get_message(р["id"])
    if rec is None or camp is None:
        итог["нет получателя/кампании"] += 1
        continue
    try:
        mid = snd.pick_mailbox(rec, camp, message=msg)
    except Exception as ex:
        итог["ОШИБКА подбора: %s" % str(ex)[:40]] += 1
        continue
    if mid:
        итог["ящик найден"] += 1
    else:
        итог["ЯЩИК НЕ НАЙДЕН"] += 1
        if len(примеры) < 5:
            примеры.append((р["id"], р["campaign_id"], getattr(rec, "email", "")))
for k, v in итог.most_common():
    print("  %-40s %d" % (k, v))
for i, k, e in примеры:
    print("     без ящика: msg#%s камп %s %s" % (i, k, e))

print("\n=== ИТОГ ===")
print("  сейчас на сервере: %s" % datetime.now().strftime("%H:%M:%S %d.%m"))
ov = store.get_setting("sending_window")
print("  окно: %s" % ov)
print("  писем запланировано: %d" % sum(нужно.values()))
print("  суммарная свободная ёмкость: %d" % sum(ём.values()))
