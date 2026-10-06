# -*- coding: utf-8 -*-
"""Что лежит в карточке отправленного письма Meyer: структура паспорта."""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)
    р = c.execute(
        "SELECT r.id, r.panel_json, m.id mid, m.mailbox_id, m.sent_at "
        "  FROM confirm_reviews r JOIN messages m ON r.message_id = m.id "
        " WHERE m.status='sent' AND (%s) AND r.panel_json IS NOT NULL "
        " ORDER BY m.id DESC LIMIT 1" % усл).fetchone()
    if not р:
        raise SystemExit("не нашлось отправленного письма Meyer с карточкой")
    print("письмо %s, ящик %s, %s" % (р["mid"], р["mailbox_id"], str(р["sent_at"])[:16]))
    д = json.loads(р["panel_json"])
    print("")
    print("--- верхние ключи карточки ---")
    for к in sorted(д):
        з = д[к]
        тип = type(з).__name__
        если = ("%d ключей" % len(з)) if isinstance(з, dict) else (
            "%d шт" % len(з) if isinstance(з, list) else str(з)[:60])
        print("   %-20s %-6s %s" % (к, тип, если))
    for раздел in ("company", "company_full", "contact", "signal", "kb"):
        б = д.get(раздел) or {}
        print("")
        print("--- %s ---" % раздел)
        for к in sorted(б):
            з = б[к]
            s = json.dumps(з, ensure_ascii=False) if isinstance(з, (dict, list)) else str(з or "")
            print("   %-20s %s" % (к, s[:110]))
print("")
print("=" * 74)
print("=== СТРУКТУРА ПАСПОРТА ===")
