# -*- coding: utf-8 -*-
"""Откуда взялся класс «только ОКВЭД»: по кампаниям и по времени.

Он конвертит наравне с полным паспортом, и это подозрительно. Проверяем,
не ранняя ли это отобранная руками партия, а не честное сравнение.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
store = Store(r"C:\sender\sender.db")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)
по_классам = {1: Counter(), 2: Counter(), 3: Counter(), 4: Counter()}
месяцы = {1: Counter(), 2: Counter(), 3: Counter(), 4: Counter()}
with store._lock:
    c = store._conn
    for р in c.execute(
            "SELECT m.campaign_id, m.sent_at, cr.panel_json FROM messages m "
            "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
            " WHERE m.status='sent' AND (%s)" % усл):
        к = 4
        if р["panel_json"]:
            try:
                д = json.loads(р["panel_json"])
            except Exception:                                   # noqa: BLE001
                д = {}
            комп, полно = д.get("company") or {}, д.get("company_full") or {}
            вид = полно.get("site_view") or {}
            сайт = str(комп.get("site") or вид.get("site") or "").strip()
            опис = str(полно.get("activity") or "").strip()
            к = 1 if полно.get("activity_verified") else (
                2 if сайт else (3 if опис else 4))
        по_классам[к][р["campaign_id"]] += 1
        месяцы[к][str(р["sent_at"])[:7]] += 1

    имена = {р["id"]: р["name"] for р in c.execute("SELECT id, name FROM campaigns")}

for к in (1, 2, 3, 4):
    print("")
    print("--- класс %d: писем %d ---" % (к, sum(по_классам[к].values())))
    for камп, n in по_классам[к].most_common(5):
        print("   кампания %-4s %-30s %5d" % (камп, str(имена.get(камп))[:30], n))
    print("   по месяцам: %s"
          % ", ".join("%s:%d" % (м, n) for м, n in sorted(месяцы[к].items())))
print("")
print("=" * 74)
print("=== ОТКУДА КЛАССЫ ===")
