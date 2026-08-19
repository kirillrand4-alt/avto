# -*- coding: utf-8 -*-
"""Где сейчас мейеровская партия: сгенерировано, на рецензии, одобрено, ушло."""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                       # noqa: E402
from sender.store import Store                                         # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for камп, имя in ((11, "Meyer"), (10, "КЦ")):
    print(f"\n== кампания {камп} ({имя}) ==")
    with store._lock:
        реш = store._conn.execute(
            "SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=? "
            "GROUP BY status", (камп,)).fetchall()
        сег = store._conn.execute(
            "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=? "
            "AND date(created_at)=date('now')", (камп,)).fetchone()[0]
        ушло = store._conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
            "ON c.message_id=m.id WHERE c.campaign_id=? AND m.status='sent' "
            "AND date(m.sent_at)=date('now')", (камп,)).fetchone()[0]
        всего_ушло = store._conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
            "ON c.message_id=m.id WHERE c.campaign_id=? AND m.status='sent'",
            (камп,)).fetchone()[0]
    print("  карточки:", {str(a): int(b) for a, b in реш})
    print(f"  создано сегодня: {сег} | ушло сегодня: {ушло} | ушло всего: {всего_ушло}")
