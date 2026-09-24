# -*- coding: utf-8 -*-
"""Что оператор видит в ленте против того, что написал клиент.

Лента лидов показывает need.slice(0, 80) — восемьдесят знаков. Логи
событий показывают первую строку, обрезанную по 80. Проверяем на
карточках, которые помечены «не интересно» при горячем вердикте:
что было видно и что за этим стояло.
"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    # все ответы Сташевского по времени
    print("--- все входящие от получателя 33048 (Сташевское) ---")
    for р in c.execute(
            "SELECT id, event_type, event_ts FROM events "
            " WHERE recipient_id=33048 ORDER BY id"):
        print("   #%-7s %-12s %s" % (р["id"], р["event_type"],
                                     str(р["event_ts"])[:19]))

    print("")
    print("=" * 74)
    print("--- карточки «не интересно» с горячим ответом: видно / было ---")
    for р in c.execute(
            "SELECT id, company_name, need, reply_kind, updated_at FROM leads "
            " WHERE status='not_interested' AND reply_kind='interested' "
            " ORDER BY id DESC"):
        нужда = " ".join(str(р["need"] or "").split())
        print("")
        print("   лид %s — %s" % (р["id"], str(р["company_name"])[:40]))
        print("      ВИДНО В ЛЕНТЕ: «%s»" % нужда[:80])
        хвост = нужда[80:400]
        if хвост.strip():
            print("      СКРЫТО:        «%s»" % хвост)
        else:
            print("      СКРЫТО:        (ничего, ответ короткий)")
print("")
print("=" * 74)
print("=== ЧТО ВИДНО В ЛЕНТЕ ===")
