# -*- coding: utf-8 -*-
"""Остановить автоотправку и показать, что осталось в очереди.

Владелец 20.08: «останови, проверь». Заслон, которым я перекидывал письма
в отправку, отбраковывал только адреса с УЖЕ вынесенным приговором пробы.
Адрес, которого проба не касалась, проходил как чистый — а владелец
просил перекидывать только проверенные.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.auto_send import ENABLED_KEY                         # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
было = store.get_setting(ENABLED_KEY, False)
store.set_setting(ENABLED_KEY, False)
стало = store.get_setting(ENABLED_KEY, False)
print(f"автоотправка: было {было} -> стало {стало}")

with store._lock:
    for s, n in store._conn.execute(
            "SELECT m.status, COUNT(*) n FROM messages m "
            "JOIN confirm_reviews r ON r.message_id=m.id "
            "WHERE r.status IN ('approved','edited') "
            "AND m.status IN ('scheduled','sending') GROUP BY m.status"):
        print(f"  {s}: {n}")
