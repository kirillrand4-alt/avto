# -*- coding: utf-8 -*-
"""Скольким компаниям Meyer писали письмо по паспорту с их сайта.

«Паспорт с сайта» в карточке письма — это подтверждённый сайт компании:
company.site непустой (он же site_view.site, заполняется только при
verified) и описание деятельности, снятое разбором страниц. Разделяем три
уровня, потому что они разного веса:

  1. САЙТ ПОДТВЕРЖДЁН  — сайт тот самый (ИНН на странице либо имя в домене),
                         профиль снят с него: письмо писалось по паспорту.
  2. РАЗБОР БЕЗ СВЕРКИ — описание снято разбором сайта, но сам сайт не
                         подтверждён: карточка сама помечает «НЕ ПРОВЕРЕНО».
  3. БЕЗ САЙТА         — только ОКВЭД и база обзвона.

Считаем по отправленным письмам с ящиков Meyer за всё время, компании —
по ИНН.
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

компании = {}          # инн -> лучший уровень (1 лучше 3)
без_карточки = set()
писем = 0
кампании = Counter()
with store._lock:
    c = store._conn
    for р in c.execute(
            "SELECT m.id, m.campaign_id, r.inn, r.email, cr.panel_json "
            "  FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
            " WHERE m.status='sent' AND (%s)" % усл):
        писем += 1
        кампании[р["campaign_id"]] += 1
        ключ = (р["inn"] or "").strip() or ("@" + str(р["email"] or "").split("@")[-1])
        if not р["panel_json"]:
            без_карточки.add(ключ)
            компании.setdefault(ключ, 9)
            continue
        try:
            д = json.loads(р["panel_json"])
        except Exception:                                       # noqa: BLE001
            без_карточки.add(ключ)
            компании.setdefault(ключ, 9)
            continue
        комп = д.get("company") or {}
        полно = д.get("company_full") or {}
        вид = полно.get("site_view") or {}
        сайт = str(комп.get("site") or вид.get("site") or "").strip()
        активность = str(полно.get("activity") or "").strip()
        примечание = str(полно.get("activity_note") or "")
        если_сайт = 1 if сайт else (
            2 if (активность and ("сайт" in примечание.lower()
                                  or полно.get("activity_verified"))) else 3)
        прежний = компании.get(ключ, 9)
        компании[ключ] = min(прежний, если_сайт)

свод = Counter(компании.values())
print("--- письма Meyer по кампаниям ---")
with store._lock:
    for к, n in sorted(кампании.items()):
        имя = store._conn.execute("SELECT name FROM campaigns WHERE id=?",
                                  (к,)).fetchone()
        print("   кампания %-4s %-32s %6d писем"
              % (к, str(имя["name"] if имя else "")[:32], n))
print("")
print("=" * 74)
print("=== ПИСЬМА MEYER ПО ПАСПОРТУ С САЙТА (за всё время) ===")
print("   писем отправлено:            %6d" % писем)
print("   компаний (по ИНН):           %6d" % len(компании))
print("")
print("   1. сайт подтверждён:         %6d  (%.1f%%)"
      % (свод.get(1, 0), 100.0 * свод.get(1, 0) / len(компании) if компании else 0))
print("   2. разбор сайта без сверки:  %6d  (%.1f%%)"
      % (свод.get(2, 0), 100.0 * свод.get(2, 0) / len(компании) if компании else 0))
print("   3. без сайта, только ОКВЭД:  %6d  (%.1f%%)"
      % (свод.get(3, 0), 100.0 * свод.get(3, 0) / len(компании) if компании else 0))
print("   карточки письма не осталось: %6d" % свод.get(9, 0))
