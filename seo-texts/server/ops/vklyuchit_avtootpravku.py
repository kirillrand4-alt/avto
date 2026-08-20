# -*- coding: utf-8 -*-
"""Включить автоотправку обратно и показать очередь.

Владелец 20.08: «запускаем как есть сейчас тогда сегодняшние» — решение
принято с открытыми цифрами: 2.3% отбивок на mail.ru, проба там слепа.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.auto_send import ENABLED_KEY                         # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
было = store.get_setting(ENABLED_KEY, False)
store.set_setting(ENABLED_KEY, True)
print(f"автоотправка: было {было} -> стало {store.get_setting(ENABLED_KEY, False)}")

with store._lock:
    for s, n in store._conn.execute(
            "SELECT m.status, COUNT(*) n FROM messages m "
            "JOIN confirm_reviews r ON r.message_id=m.id "
            "WHERE r.status IN ('approved','edited') "
            "AND m.status IN ('scheduled','sending') GROUP BY m.status"):
        print(f"  {s}: {n}")
