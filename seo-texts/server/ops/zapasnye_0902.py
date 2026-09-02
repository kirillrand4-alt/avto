# -*- coding: utf-8 -*-
"""Только чтение: почему перелив в яндексовые ящики не срабатывает."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.store import Store                # noqa: E402
from sender.suppression import Suppression    # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
import sender.sender as S                     # noqa: E402
import sender.gates as G                      # noqa: E402

print("=== _zapasnye_yashchiki ===")
print(inspect.getsource(S.Sender._zapasnye_yashchiki)[:2400])

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store), cards=карт)
ящ = {m["mailbox_id"]: m for m in cfg.get("mailboxes", [])}

print("\n=== ЧТО ВЕРНЁТ ДЛЯ ПУЛА mail.ru ===")
пулы = cfg.provider_pools()
зап = snd._zapasnye_yashchiki(пулы.get("pool_mailru", []))
print("  запасных ящиков: %d" % len(зап or []))
for x in (зап or [])[:12]:
    print("    %-36s %s" % (x, ящ.get(x, {}).get("division")))
