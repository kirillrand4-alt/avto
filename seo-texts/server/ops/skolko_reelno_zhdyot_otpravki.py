# -*- coding: utf-8 -*-
"""Сколько писем РЕАЛЬНО ждёт отправки, а сколько уже ушло.

Вопрос владельца: «980 готовые завтра отправиться? или с теми, которые
были отправлены сегодня». Число 980 - это строки confirm_reviews со
статусом approved, и оно НЕ уменьшается после отправки: решение оператора
остаётся в истории, а отправка живёт в messages. Поэтому считаем по
messages, а не по решениям.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    решения = Counter(dict(store._conn.execute(
        "SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=10 "
        "GROUP BY status").fetchall()))
    письма = Counter(dict(store._conn.execute(
        "SELECT m.status, COUNT(*) FROM messages m "
        "JOIN confirm_reviews c ON c.message_id=m.id "
        "WHERE c.campaign_id=10 GROUP BY m.status").fetchall()))
    ждут = store._conn.execute(
        "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
        "ON c.message_id=m.id WHERE c.campaign_id=10 "
        "AND c.status='approved' AND m.status='scheduled'").fetchone()[0]
    ушли_сегодня = store._conn.execute(
        "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
        "ON c.message_id=m.id WHERE c.campaign_id=10 AND m.status='sent' "
        "AND date(m.sent_at)=date('now')").fetchone()[0]
    ушли_всего = store._conn.execute(
        "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
        "ON c.message_id=m.id WHERE c.campaign_id=10 "
        "AND m.status='sent'").fetchone()[0]

print("решения оператора (confirm_reviews, кампания 10):")
for k, n in решения.most_common():
    print(f"  {n:>5}  {k}")
print("\nсами письма (messages):")
for k, n in письма.most_common():
    print(f"  {n:>5}  {k}")
print(f"\nждут отправки (approved + scheduled): {ждут}")
print(f"уже отправлено всего: {ушли_всего}, из них сегодня: {ушли_сегодня}")
