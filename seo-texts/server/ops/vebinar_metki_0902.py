# -*- coding: utf-8 -*-
"""Только чтение: кто из наших 175 заблокирован меткой kc и как её читает индекс."""
import inspect
import sqlite3
import sys

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
камп = store.get_campaign(12)

try:
    print("=== ObzvonIndex.divisions ===")
    print(inspect.getsource(карт._obzvon.divisions)[:1500])
except Exception as ex:
    print("  не прочитать: %s" % str(ex)[:120])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row

плохие = []
for р in c.execute("SELECT id, recipient_id FROM messages WHERE campaign_id=12"):
    rec = store.get_recipient(р["recipient_id"])
    msg = store.get_message(р["id"])
    б = snd.division_block(rec, "a.tyunin@sort-systems.ru", message=msg)
    if б and б.startswith("division_mismatch"):
        стр = o.execute("SELECT division, name_short, equip_categories FROM obzvon"
                        " WHERE inn=?", (rec.inn,)).fetchone()
        плохие.append((rec.inn, rec.email, rec.company_name,
                       стр["division"] if стр else "нет строки",
                       (стр["equip_categories"] if стр else "")))

print("\n=== ЗАБЛОКИРОВАНЫ МЕТКОЙ (%d) ===" % len(плохие))
for inn, поч, ком, див, об in плохие:
    print("  %-12s %-30s %-26s метка=%-6s потребности=%s"
          % (inn, поч[:30], str(ком)[:26], див, str(об)[:24]))
