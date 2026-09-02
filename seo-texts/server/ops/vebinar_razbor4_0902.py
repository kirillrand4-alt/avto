# -*- coding: utf-8 -*-
"""Только чтение: проверяет ли send() направление; что с меткой наших компаний."""
import inspect
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
import sender.sender as S                     # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")

print("=== ПРОВЕРЯЕТ ЛИ send() НАПРАВЛЕНИЕ ===")
исх = inspect.getsource(S.Sender.send)
for м in re.finditer(r"division_block|_napravlenie_pisma", исх):
    н = исх[:м.start()].count("\n")
    print("  send()+%d: %s" % (н + 1, исх.splitlines()[н].strip()[:96]))
print("  (пусто = send направление не проверяет, решает только подбор)")

print("\n=== ТУМБЛЕР «СЛАТЬ ВНЕ БАЗЫ» ===")
for к in ("obzvon.vne_bazy", "obzvon.send_outside", "confirm.vne_bazy",
          "gates.vne_bazy", "obzvon"):
    зн = cfg.get(к, "НЕТ")
    if зн != "НЕТ":
        print("  %-24s %s" % (к, str(dict(зн) if hasattr(зн, 'keys') else зн)[:150]))
исх2 = inspect.getsource(S.Sender.division_block)
н = исх2.find("вне базы")
print("  ...%s" % исх2[max(0, н - 200):н + 700].replace("\n", "\n  ")[:900])

print("\n=== МЕТКА НАШИХ КОМПАНИЙ В ИНДЕКСЕ ОБЗВОНА ===")
карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
из = {"meyer": 0, "kc": 0, "kc+meyer": 0, "None": 0, "без ИНН": 0}
for р in c.execute("SELECT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.campaign_id=12"):
    if not р["inn"]:
        из["без ИНН"] += 1
        continue
    d = карт.division(р["inn"])
    из[str(d)] = из.get(str(d), 0) + 1
for k, v in sorted(из.items(), key=lambda x: -x[1]):
    print("  %-12s %3d" % (k, v))

o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row
print("\n=== ИНДЕКС ОБЗВОНА ===")
кол = [r["name"] for r in o.execute("PRAGMA table_info(obzvon)")]
print("  колонки: %s" % ", ".join(кол))
for р in o.execute("SELECT division, COUNT(*) n FROM obzvon GROUP BY division"):
    print("  %-12s %6d" % (р["division"], р["n"]))
