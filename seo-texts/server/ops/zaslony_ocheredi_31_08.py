# -*- coding: utf-8 -*-
"""Только чтение: опрос боевого заслона по всем письмам очереди."""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.confirm import ConfirmSend    # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

ряды = list(s.execute(
    "SELECT m.id, m.campaign_id, r.inn, r.email FROM messages m"
    " JOIN recipients r ON r.id=m.recipient_id WHERE m.status='scheduled'"))
print("=== ОПРОС ЗАСЛОНА ПО %d ПИСЬМАМ ОЧЕРЕДИ ===" % len(ряды))
c = Counter()
примеры = {}
for р in ряды:
    try:
        п = cs._guard(inn=str(р["inn"] or ""), email=str(р["email"] or ""))
    except Exception as ex:
        c["ОШИБКА: %s" % str(ex)[:40]] += 1
        continue
    if п:
        к = str(п).split(":")[0][:44]
        c[к] += 1
        примеры.setdefault(к, []).append((р["id"], р["email"]))
    else:
        c["свободно"] += 1
for k, v in c.most_common():
    print("  %-46s %5d" % (k, v))
for k, лст in примеры.items():
    print("\n  примеры «%s»:" % k)
    for i, e in лст[:4]:
        print("     msg#%-7s %s" % (i, e))

print("\n=== ИТОГ ===")
своб = c.get("свободно", 0)
print("  писем в очереди: %d" % len(ряды))
print("  пройдут заслон : %d" % своб)
print("  будут сняты    : %d" % (len(ряды) - своб))
print("  ёмкость meyer сегодня 460, значит уйдёт сегодня не больше 460,")
print("  остальное перенесётся на следующий день")
