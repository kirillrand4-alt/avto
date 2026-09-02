# -*- coding: utf-8 -*-
"""Только чтение: сколько писем партии вообще некому отправить."""
import datetime as dt
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
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
теперь = dt.datetime.now(dt.timezone.utc)
пулы = cfg.provider_pools()
ящ = {m["mailbox_id"]: m for m in cfg.get("mailboxes", [])}

print("=== СОСТАВ ПУЛОВ ===")
for имя, сп in пулы.items():
    м = [x for x in сп if str(ящ.get(x, {}).get("division")) == "meyer"]
    print("  %-16s всего %2d, из них meyer %2d" % (имя, len(сп), len(м)))

for кид in (12, 11):
    камп = store.get_campaign(кид)
    ряды = list(c.execute("SELECT id, recipient_id FROM messages WHERE campaign_id=?"
                          " AND status='scheduled'", (кид,)))
    пул_счёт, годн_счёт = Counter(), Counter()
    без = 0
    for р in ряды:
        rec = store.get_recipient(р["recipient_id"])
        msg = store.get_message(р["id"])
        пул = snd._route_pool(rec, камп)
        пул_счёт[пул] += 1
        мвп = [x for x in (пулы.get(пул) or [])
               if str(ящ.get(x, {}).get("division")) == "meyer"]
        if not мвп:
            годн_счёт["в пуле нет meyer-ящиков"] += 1
            без += 1
            continue
        г = [x for x in мвп if snd.division_block(rec, x, message=msg) is None]
        if not г:
            годн_счёт["все ящики режет гейт направления"] += 1
            без += 1
        elif not [x for x in г if snd.can_send_now(x, now=теперь)]:
            годн_счёт["ящики есть, но сейчас заняты/лимит"] += 1
        else:
            годн_счёт["можно слать сейчас"] += 1
    print("\n=== КАМПАНИЯ %d: %d писем в очереди ===" % (кид, len(ряды)))
    for k, v in пул_счёт.most_common():
        print("  пул %-16s %4d" % (k, v))
    for k, v in годн_счёт.most_common():
        print("  %-38s %4d" % (k, v))
    print("  НЕКОМУ ОТПРАВИТЬ В ПРИНЦИПЕ: %d из %d" % (без, len(ряды)))
