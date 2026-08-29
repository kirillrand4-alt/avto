# -*- coding: utf-8 -*-
"""Что ловил бы СТАРЫЙ отбор: сколько стопов пропускал флаг в карточке."""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
стоп = {str(r["value"]).strip().lower() for r in
        c.execute("SELECT value FROM suppression")}
всего = c.execute("SELECT COUNT(*) FROM recipients WHERE suppressed=0"
                  ).fetchone()[0]
плохих = c.execute(
    "SELECT COUNT(*) FROM recipients r WHERE r.suppressed=0 AND ("
    "  LOWER(r.email) IN (SELECT LOWER(value) FROM suppression) OR "
    "  r.inn IN (SELECT value FROM suppression))").fetchone()[0]
print("получателей с флагом «не в стоп-листе»: %d" % всего)
print("из них РЕАЛЬНО в таблице стоп-листа:    %d" % плохих)
print("   то есть старый отбор считал годными %d карточек, которые уже под запретом"
      % плохих)
print("\nсегменты, где это заметнее всего:")
for r in c.execute(
        "SELECT r.segment, COUNT(*) n FROM recipients r "
        " WHERE r.suppressed=0 AND (LOWER(r.email) IN "
        "       (SELECT LOWER(value) FROM suppression) OR r.inn IN "
        "       (SELECT value FROM suppression)) "
        " GROUP BY 1 ORDER BY 2 DESC LIMIT 8"):
    print("   %-28s %d" % (str(r["segment"])[:28], r["n"]))
c.close()
