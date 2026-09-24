# -*- coding: utf-8 -*-
"""Кто и когда переводит карточки в «не интересно»: руками или само."""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    print("--- переходы статуса: кто → куда ---")
    for р in c.execute(
            "SELECT COALESCE(actor_user_id,'(нет)') кто, to_status, COUNT(*) n "
            "  FROM lead_events WHERE action='status_changed' "
            " GROUP BY 1,2 ORDER BY 3 DESC LIMIT 15"):
        print("   актор %-6s → %-18s %5d" % (р["кто"], р["to_status"], р["n"]))

    print("")
    print("--- переходы в «не интересно» по дням и часам ---")
    по_дням = Counter()
    часы = Counter()
    for р in c.execute(
            "SELECT created_at FROM lead_events "
            " WHERE action='status_changed' AND to_status='not_interested'"):
        с = str(р["created_at"])
        по_дням[с[:10]] += 1
        часы[с[11:13]] += 1
    for д in sorted(по_дням)[-12:]:
        print("   %s  %4d" % (д, по_дням[д]))
    print("")
    print("   по часам (UTC): %s"
          % ", ".join("%s:%d" % (ч, n) for ч, n in sorted(часы.items())))

    print("")
    print("--- пачки: сколько переходов в одну и ту же секунду ---")
    пачки = Counter()
    for р in c.execute(
            "SELECT created_at FROM lead_events "
            " WHERE action='status_changed' AND to_status='not_interested'"):
        пачки[str(р["created_at"])[:19]] += 1
    крупные = [(к, n) for к, n in пачки.items() if n > 1]
    крупные.sort(key=lambda x: -x[1])
    print("   секунд, где больше одного перехода: %d" % len(крупные))
    for к, n in крупные[:10]:
        print("      %s  %d карточек разом" % (к, n))

    print("")
    print("--- пользователи панели ---")
    try:
        for р in c.execute("SELECT id, username, role FROM users ORDER BY id"):
            print("   #%-3s %-20s %s" % (р["id"], р["username"], р["role"]))
    except Exception as ex:                                     # noqa: BLE001
        print("   таблицы users нет: %s" % str(ex)[:60])

    print("")
    print("--- какие статусы вообще бывают и сколько их ---")
    for р in c.execute("SELECT status, COUNT(*) n FROM leads GROUP BY 1 "
                       " ORDER BY 2 DESC"):
        print("   %-18s %5d" % (р["status"], р["n"]))
print("")
print("=" * 74)
print("=== КТО ГАСИТ ЛИДЫ ===")
