# -*- coding: utf-8 -*-
"""Только чтение: боевой подбор ящика для кампании 12 с живым индексом обзвона."""
import io
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
import sender.sender as S                   # noqa: E402
import sender.gates as G                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
print("индекс обзвона активен: %s" % getattr(карт, "active", None))
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store), cards=карт)

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
ряды = list(c.execute("SELECT id, recipient_id, mailbox_id FROM messages"
                      " WHERE campaign_id=12 AND status='scheduled'"
                      " ORDER BY id LIMIT 40"))
camp = store.get_campaign(12)
мейер = {m["mailbox_id"] for m in cfg.get("mailboxes", [])
         if str(m.get("division")) == "meyer"}

# как зовёт оркестратор: БЕЗ message
безс, сс = Counter(), Counter()
for р in ряды:
    rec = store.get_recipient(р["recipient_id"])
    msg = store.get_message(р["id"])
    try:
        безс[snd.pick_mailbox(rec, camp) or "НЕ НАЙДЕН"] += 1
    except Exception as ex:
        безс["ОШИБКА %s" % str(ex)[:40]] += 1
    try:
        сс[snd.pick_mailbox(rec, camp, message=msg) or "НЕ НАЙДЕН"] += 1
    except Exception as ex:
        сс["ОШИБКА %s" % str(ex)[:40]] += 1

print("\n=== КАК ЗОВЁТ ОРКЕСТРАТОР (без message) ===")
for k, v in безс.most_common():
    print("  %-40s %3d %s" % (k[:40], v, "" if k in мейер or k == "НЕ НАЙДЕН" else "<-- НЕ MEYER"))
print("\n=== ЕСЛИ ПЕРЕДАТЬ message ===")
for k, v in сс.most_common():
    print("  %-40s %3d %s" % (k[:40], v, "" if k in мейер or k == "НЕ НАЙДЕН" else "<-- НЕ MEYER"))

print("\n=== ГЕЙТ НА КОНКРЕТНОМ ПИСЬМЕ ===")
rec = store.get_recipient(ряды[0]["recipient_id"])
msg = store.get_message(ряды[0]["id"])
for я in ("a.tyunin@sort-systems.ru", "a.balakirev@compressor-store.ru"):
    print("  %-34s без message=%s | с message=%s"
          % (я, snd.division_block(rec, я), snd.division_block(rec, я, message=msg)))

print("\n=== ХОЛД: dry_run оркестратора ===")
т = io.open(r"C:\sender\sender\wiring.py", encoding="utf-8", errors="replace").read()
for м in re.finditer(r"dry_run", т):
    н = т[:м.start()].count("\n")
    с = т.splitlines()[н].strip()
    if not с.startswith("#"):
        print("  wiring.py:%d  %s" % (н + 1, с[:96]))
print("  confirm.live_send = %s" % cfg.get("confirm.live_send", None))
print("  service.dry_run    = %s" % cfg.get("service.dry_run", None))
