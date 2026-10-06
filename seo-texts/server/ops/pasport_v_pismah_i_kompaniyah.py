# -*- coding: utf-8 -*-
"""Паспорт компании в письмах Meyer: по письмам И по компаниям, по каждому признаку.

Владелец помнит «около 3000 писем по паспорту компании». Считаем все
разумные признаки «паспорта» сразу, и в письмах, и в компаниях, чтобы
стало видно, какой из них даёт эту цифру.
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

ПРИЗНАКИ = [
    "карточка письма есть",
    "сайт подтверждён в карточке",
    "описание снято с подтверждённого сайта",
    "описание есть хоть какое-то",
    "контакт: сайт сверен",
    "роль человека определена",
    "имя человека известно",
    "обогащение по компании вообще было",
    "выручка известна (отчётность)",
    "письмо собрано ИИ по карточке",
]
письма = Counter()
компании = {к: set() for к in ПРИЗНАКИ}
всего_писем = 0
все_компании = set()

with store._lock:
    for р in store._conn.execute(
            "SELECT r.inn, r.email, cr.panel_json FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
            " WHERE m.status='sent' AND (%s)" % усл):
        всего_писем += 1
        ключ = (р["inn"] or "").strip() or ("@" + str(р["email"] or "").split("@")[-1])
        все_компании.add(ключ)
        if not р["panel_json"]:
            continue
        try:
            д = json.loads(р["panel_json"])
        except Exception:                                       # noqa: BLE001
            continue
        комп = д.get("company") or {}
        полно = д.get("company_full") or {}
        конт = д.get("contact") or {}
        вид = полно.get("site_view") or {}

        есть = {
            "карточка письма есть": True,
            "сайт подтверждён в карточке":
                bool(str(комп.get("site") or вид.get("site") or "").strip()),
            "описание снято с подтверждённого сайта":
                bool(полно.get("activity_verified")),
            "описание есть хоть какое-то":
                bool(str(полно.get("activity") or "").strip()),
            "контакт: сайт сверен": bool(конт.get("site_confirmed")),
            "роль человека определена":
                str(конт.get("role") or "") not in ("", "не определена", "no_data"),
            "имя человека известно": bool(str(конт.get("person") or "").strip()),
            "обогащение по компании вообще было": bool(полно.get("available")),
            "выручка известна (отчётность)": bool(комп.get("revenue")),
            "письмо собрано ИИ по карточке": bool(д.get("ai")),
        }
        for к, v in есть.items():
            if v:
                письма[к] += 1
                компании[к].add(ключ)

print("   %-42s %7s %9s" % ("признак «паспорта»", "писем", "компаний"))
for к in ПРИЗНАКИ:
    print("   %-42s %7d %9d" % (к, письма[к], len(компании[к])))
print("")
print("=" * 74)
print("=== ПАСПОРТ В ПИСЬМАХ MEYER ===")
print("   писем отправлено всего:  %6d" % всего_писем)
print("   компаний всего:          %6d" % len(все_компании))
