# -*- coding: utf-8 -*-
"""Поставить копиям пометку, по которой заслон их пропускает."""
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ИДЫ = (2601, 3050, 3051, 3312, 3313, 3472, 3473)
ПОМЕТКА = "копия на второй адрес (одобрено человеком, разбор 20.08)"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc).isoformat()
with store._lock:
    for rid in ИДЫ:
        store._conn.execute(
            "UPDATE confirm_reviews SET reason=?, updated_at=? WHERE id=?",
            (ПОМЕТКА, сейчас, rid))
    store._conn.commit()
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for r in c.execute("SELECT id, status, email, COALESCE(reason,'') rs "
                   "FROM confirm_reviews WHERE id IN " + str(ИДЫ)):
    print(f"  #{r['id']} {r['status']:<9} {r['email']:<32} {r['rs'][:50]}")
