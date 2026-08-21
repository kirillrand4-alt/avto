# -*- coding: utf-8 -*-
"""Список карточек вебинара: номер, компания, адресат, вариант текста.

Вариант узнаём по теме письма - четыре текста владельца различаются ею,
а хранить отдельную пометку варианта незачем.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    строки = store._conn.execute(
        "SELECT r.id, r.status, r.subject, r.email, rc.company_name, "
        "       rc.contact_name "
        "  FROM confirm_reviews r "
        "  LEFT JOIN recipients rc ON rc.id = r.recipient_id "
        " WHERE r.dedup_key LIKE 'vebinar28:%' ORDER BY r.id").fetchall()

темы, номера = {}, {}
for с in строки:
    if с[2] not in темы:
        темы[с[2]] = len(темы) + 1
print(f"карточек вебинара: {len(строки)}, "
      f"номера с №{строки[0][0]} по №{строки[-1][0]}\n")
print("вариант | тема")
for т, н in темы.items():
    print(f"   {н}    | {т}")
print()
for с in строки:
    номера.setdefault(темы[с[2]], []).append(с[0])
    print(f"№{с[0]} в{темы[с[2]]} {с[1]:8} {(с[4] or '?')[:34]:34} "
          f"{(с[5] or '')[:26]:26} {с[3]}")
print()
for н, сп in sorted(номера.items()):
    print(f"вариант {н}: {len(сп)} писем")
