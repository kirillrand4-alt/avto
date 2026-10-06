# -*- coding: utf-8 -*-
"""Сколько КОМПАНИЙ получили письмо с описанием, снятым с их сайта.

Плюс живые примеры этих описаний — чтобы видеть, что это действительно
текст со страниц, а не расшифровка кода ОКВЭД.
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

с_сайта, все_компании, примеры = set(), set(), []
with store._lock:
    for р in store._conn.execute(
            "SELECT r.inn, r.email, r.company_name, cr.panel_json "
            "  FROM messages m JOIN recipients r ON m.recipient_id = r.id "
            "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
            " WHERE m.status='sent' AND (%s)" % усл):
        ключ = (р["inn"] or "").strip() or ("@" + str(р["email"] or "").split("@")[-1])
        все_компании.add(ключ)
        if not р["panel_json"]:
            continue
        try:
            д = json.loads(р["panel_json"])
        except Exception:                                       # noqa: BLE001
            continue
        полно = д.get("company_full") or {}
        if not полно.get("activity_verified"):
            continue
        с_сайта.add(ключ)
        if len(примеры) < 6:
            примеры.append((str(р["company_name"])[:34],
                            " ".join(str(полно.get("activity") or "").split())[:200],
                            str((д.get("company") or {}).get("site") or "")[:40]))

print("--- примеры описаний, снятых с подтверждённого сайта ---")
for имя, акт, сайт in примеры:
    print("")
    print("   %s   [%s]" % (имя, сайт or "сайт не записан"))
    print("      %s" % акт)
print("")
print("=" * 74)
print("=== КОМПАНИИ MEYER С ОПИСАНИЕМ С ИХ САЙТА ===")
print("   компаний, которым писали всего:        %5d" % len(все_компании))
print("   из них описание снято с их сайта:      %5d  (%.1f%%)"
      % (len(с_сайта), 100.0 * len(с_сайта) / len(все_компании) if все_компании else 0))
