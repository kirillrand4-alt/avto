# -*- coding: utf-8 -*-
"""Только чтение: финальный вид писем после согласования рода и подписи."""
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
RM = S.RenderedMessage

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
n = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND"
              " body_rendered LIKE '%посторонними включениями%'").fetchone()[0]
n2 = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND"
               " (body_rendered LIKE '%металлодетектор%')").fetchone()[0]
print("=== ПРОВЕРКА ПО КАМПАНИИ 12 ===")
print("  писем всего: %d" % c.execute("SELECT COUNT(*) FROM messages"
                                      " WHERE campaign_id=12").fetchone()[0])
print("  с оборотом «посторонними включениями»: %d" % n)
print("  со словом «металлодетектор»: %d" % n2)
print("  (в прошлом отчёте цифра 538 была ошибкой моего запроса: OR вышел"
      " за скобку кампании и посчитал всю базу)")

for где, ящик in (("ЯЩИК ИРИНЫ", "i.kuznetsova@sort-systems.ru"),
                  ("МУЖСКОЙ ЯЩИК", "a.tyunin@sort-systems.ru")):
    усл = "mailbox_id=?" if "ИРИН" in где.upper() else "(mailbox_id IS NULL OR mailbox_id='')"
    пар = (ящик,) if "ИРИН" in где.upper() else ()
    м = c.execute("SELECT id, subject, body_rendered FROM messages"
                  " WHERE campaign_id=12 AND %s ORDER BY id LIMIT 1" % усл, пар).fetchone()
    итог = snd._apply_signature(RM(subject=м["subject"], body=м["body_rendered"]),
                                ящик, камп)
    print("\n========== %s: %s ==========" % (где, ящик))
    print("Тема: %s" % м["subject"])
    print(итог.body)
