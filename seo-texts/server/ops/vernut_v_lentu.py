# -*- coding: utf-8 -*-
"""Вернуть лиды из «не интересно» в ленту (статус new) — кроме компаний,
у которых есть лид в Bitrix. Владелец 13.10: «верни 7 в ленту, посмотрю сам,
но только не из колонки "отдали в битрикс"».

    vernut_v_lentu.py <id,id,…>
"""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.leaddesk import LeadDesk  # noqa: E402

ид = [int(x) for x in sys.argv[1].split(",")]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
desk = LeadDesk(cfg, store)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for лид in ид:
    л = c.execute("SELECT * FROM leads WHERE id=?", (лид,)).fetchone()
    if not л:
        print("#%s: нет такого" % лид)
        continue
    в_битрикс = c.execute(
        "SELECT id FROM leads WHERE status='in_bitrix' AND id<>? AND "
        "((inn<>'' AND inn=?) OR lower(email)=lower(?))", (лид, л["inn"] or "", л["email"])).fetchall()
    if в_битрикс:
        print("#%s %s: ПРОПУСК — уже в Bitrix (лид #%s)" % (лид, л["company_name"],
              ",".join(str(р[0]) for р in в_битрикс)))
        continue
    if л["status"] != "not_interested":
        print("#%s %s: статус %s — не трогаю" % (лид, л["company_name"], л["status"]))
        continue
    desk.set_status(лид, status="new")
    print("#%s %s: возвращён в ленту (new)" % (лид, л["company_name"]))
print("=== ВЕРНУТЬ В ЛЕНТУ ===")
