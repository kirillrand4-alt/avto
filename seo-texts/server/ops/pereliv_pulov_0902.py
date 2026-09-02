# -*- coding: utf-8 -*-
"""Только чтение: есть ли перелив в другой пул и что реально вернёт подбор
для наших писем на mail.ru."""
import datetime as dt
import inspect
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.store import Store                # noqa: E402
from sender.suppression import Suppression    # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
import sender.sender as S                     # noqa: E402
import sender.gates as G                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store), cards=карт)
теперь = dt.datetime.now(dt.timezone.utc)
камп = store.get_campaign(12)
ящ = {m["mailbox_id"]: m for m in cfg.get("mailboxes", [])}

исх = inspect.getsource(S.Sender.pick_mailbox)
н = исх.find("ПЕРЕЛИВ")
print("=== КОД ПЕРЕЛИВА ===")
print(исх[max(0, н - 200):н + 1500] if н >= 0 else "  упоминания перелива нет")

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
ряды = list(c.execute(
    "SELECT m.id, m.recipient_id, r.email, r.mx_provider FROM messages m"
    " JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.campaign_id=12 AND m.status='scheduled' AND r.mx_provider='mailru'"))
print("\n=== ПИСЬМА НАШЕЙ ПАРТИИ НА MAIL.RU: %d ===" % len(ряды))
итог = Counter()
примеры = []
for р in ряды:
    rec = store.get_recipient(р["recipient_id"])
    msg = store.get_message(р["id"])
    mid = snd.pick_mailbox(rec, камп, now=теперь, message=msg)
    если = mid or "НЕТ ЯЩИКА"
    итог[если] += 1
    if mid and len(примеры) < 4:
        примеры.append((р["email"], mid, str(ящ.get(mid, {}).get("division"))))
for k, v in итог.most_common():
    print("  %-38s %3d %s" % (k, v, "<- meyer" if str(ящ.get(k, {}).get("division"))
                              == "meyer" else ""))
for e, m, d in примеры:
    print("    %-30s -> %s (%s)" % (e[:30], m, d))
