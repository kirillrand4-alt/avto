# -*- coding: utf-8 -*-
"""Только чтение: пулы провайдеров, маршрутизация и разбор метки компании."""
import inspect
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
import sender.sender as S                     # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")

print("=== ПУЛЫ ПРОВАЙДЕРОВ ===")
пулы = cfg.provider_pools()
ящики = {m["mailbox_id"]: m for m in cfg.get("mailboxes", [])}
for имя, сп in пулы.items():
    м = [x for x in сп if str(ящики.get(x, {}).get("division")) == "meyer"]
    к = [x for x in сп if str(ящики.get(x, {}).get("division")) == "kc"]
    print("  %-16s всего %2d | meyer %2d | kc %2d" % (имя, len(сп), len(м), len(к)))
    print("       meyer: %s" % ", ".join(x.split("@")[0] for x in м))

print("\n=== _route_pool ===")
print(inspect.getsource(S.Sender._route_pool)[:1500])

print("\n=== CompanyCards.divisions ===")
ф = getattr(CompanyCards, "divisions", None)
if ф:
    print(inspect.getsource(ф)[:1600])
else:
    print("  метода нет, работает старый путь через division()")
