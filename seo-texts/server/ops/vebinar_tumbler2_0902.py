# -*- coding: utf-8 -*-
"""Только чтение: включён ли тумблер «слать вне базы» и сколько наших писем
он спасает."""
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

for мод in (S,):
    ф = getattr(мод, "razreshena_vne_bazy", None)
    if ф:
        print("=== razreshena_vne_bazy ===")
        print(inspect.getsource(ф)[:1200])
        break

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
try:
    print("  СЕЙЧАС: %s" % ф(store, cfg))
except Exception as ex:
    print("  не вычислить: %s" % str(ex)[:120])

карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store), cards=карт)
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
из = {}
for р in c.execute("SELECT m.id, m.recipient_id FROM messages m WHERE m.campaign_id=12"):
    rec = store.get_recipient(р["recipient_id"])
    msg = store.get_message(р["id"])
    б = snd.division_block(rec, "a.tyunin@sort-systems.ru", message=msg)
    из[str(б).split(":")[0]] = из.get(str(б).split(":")[0], 0) + 1
print("\n=== ГЕЙТ ПРОТИВ ПРОГРЕТОГО MEYER-ЯЩИКА (a.tyunin), все 175 ===")
for k, v in sorted(из.items(), key=lambda x: -x[1]):
    print("  %-28s %3d %s" % (k, v, "<- проходит" if k == "None" else ""))
