# -*- coding: utf-8 -*-
"""Сколько мейеровских писем создано сегодня и что с ними."""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряды = store._conn.execute(
        "SELECT status, COUNT(*) FROM confirm_reviews "
        "WHERE campaign_id=11 AND date(created_at)=date('now') "
        "GROUP BY status").fetchall()
    всего = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=11 "
        "AND date(created_at)=date('now')").fetchone()[0]
    первое, последнее = store._conn.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM confirm_reviews "
        "WHERE campaign_id=11 AND date(created_at)=date('now')").fetchone()
print(f"мейеровских писем создано сегодня: {всего}")
for st, n in ряды:
    print(f"  {n:>4}  {st}")
print(f"  с {str(первое)[11:19]} по {str(последнее)[11:19]}")
