# -*- coding: utf-8 -*-
"""Показать карточки вебинара 28.08 из очереди подтверждения.

Номер печатаем тот же, что видит оператор в панели - id строки
confirm_reviews. Первые N по порядку заведения: варианты текста шли по
кругу, поэтому десятка накрывает все четыре.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

сколько = int(sys.argv[1]) if len(sys.argv) > 1 else 10
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    строки = store._conn.execute(
        "SELECT r.id, r.email, r.subject, r.body, r.status, r.inn, "
        "       rc.company_name, rc.contact_name "
        "  FROM confirm_reviews r "
        "  LEFT JOIN recipients rc ON rc.id = r.recipient_id "
        " WHERE r.dedup_key LIKE 'vebinar28:%' "
        " ORDER BY r.id LIMIT ?", (сколько,)).fetchall()
    всего = store._conn.execute(
        "SELECT COUNT(*), SUM(status='pending') FROM confirm_reviews "
        " WHERE dedup_key LIKE 'vebinar28:%'").fetchone()

print(f"карточек вебинара всего: {всего[0]}, ждут решения: {всего[1]}\n")
for с in строки:
    print("=" * 72)
    print(f"№{с[0]}  {с[4]}  {с[6] or '?'}  |  {с[7] or 'без имени'}  "
          f"|  {с[1]}")
    print(f"Тема: {с[2]}")
    print()
    print(с[3])
    print()
