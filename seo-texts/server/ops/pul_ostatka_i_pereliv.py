# -*- coding: utf-8 -*-
"""Как остаток очереди ложится на пулы и включён ли перелив между ними.

Лимит дня у пула mail.ru меньше, чем у яндексового, а получателей на
mail.ru больше. Без перелива очередь упрётся в свой пул при свободных
ящиках соседнего.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряд = store._conn.execute(
        """SELECT COALESCE(rc.mx_provider,'?'), COUNT(*)
             FROM messages m
             JOIN confirm_reviews c ON c.message_id=m.id
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
            WHERE c.campaign_id=10 AND c.status='approved'
              AND m.status='scheduled'
            GROUP BY 1 ORDER BY 2 DESC""").fetchall()
итог = Counter(dict(ряд))
print("ждут отправки по почтовику получателя:")
for k, n in итог.most_common():
    print(f"  {n:>5}  {k}")
print(f"  всего: {sum(итог.values())}")

пс = cfg.get("provider_split", {}) or {}
print("\nprovider_split из конфига:")
for k in ("routing", "overflow", "overflow_max_bounce_pct"):
    print(f"  {k}: {пс.get(k)}")
окно = cfg.get("sending_window", {}) or {}
print("\nокно отправки:", {k: окно.get(k) for k in
                           ("days", "start", "end", "tz", "by_recipient_tz")})
