# -*- coding: utf-8 -*-
"""Доходимость до Битрикса по уровню паспорта компании.

Разбиваем компании, которым писал Meyer, на четыре класса по тому, что
знали о компании на момент письма, и смотрим, сколько из каждого класса
дошло до ответа, до карточки лида и до «передали в Битрикс».

«Передали в Битрикс» берём не по текущему статусу, а по факту захода в
него когда-либо (lead_events): карточку могли потом закрыть, но она там
была.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
КЛАССЫ = ["1. описание с подтверждённого сайта",
          "2. сайт подтверждён, описание не с него",
          "3. описание есть, сайта нет",
          "4. только название, ОКВЭД, регион"]

store = Store(r"C:\sender\sender.db")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)

класс_компании = {}
with store._lock:
    c = store._conn
    for р in c.execute(
            "SELECT r.inn, r.email, cr.panel_json FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
            " WHERE m.status='sent' AND (%s)" % усл):
        ключ = (р["inn"] or "").strip() or ("@" + str(р["email"] or "").split("@")[-1])
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
            if полно.get("activity_verified"):
                к = 1
            elif сайт:
                к = 2
            elif опис:
                к = 3
        класс_компании[ключ] = min(класс_компании.get(ключ, 9), к)

    # лиды: по ИНН, и был ли заход в Битрикс когда-либо
    лид_класс, бит_класс, лиды_инн = Counter(), Counter(), {}
    for л in c.execute("SELECT id, inn, email, status FROM leads"):
        ключ = (л["inn"] or "").strip() or ("@" + str(л["email"] or "").split("@")[-1])
        if ключ not in класс_компании:
            continue
        лиды_инн.setdefault(ключ, []).append(л["id"])
    for ключ, ид in лиды_инн.items():
        к = класс_компании[ключ]
        лид_класс[к] += 1
        был = False
        for i in ид:
            r = c.execute(
                "SELECT 1 FROM lead_events WHERE lead_id=? AND to_status='in_bitrix'"
                " LIMIT 1", (i,)).fetchone()
            if r:
                был = True
                break
            r2 = c.execute("SELECT 1 FROM leads WHERE id=? AND status='in_bitrix'",
                           (i,)).fetchone()
            if r2:
                был = True
                break
        if был:
            бит_класс[к] += 1

всего = Counter(класс_компании.values())
print("   %-42s %8s %7s %9s %8s"
      % ("класс паспорта", "компаний", "лидов", "в Битрикс", "доля"))
for i, имя in enumerate(КЛАССЫ, start=1):
    к, л, б = всего.get(i, 0), лид_класс.get(i, 0), бит_класс.get(i, 0)
    print("   %-42s %8d %7d %9d %7.2f%%"
          % (имя, к, л, б, 100.0 * б / к if к else 0))
print("")
print("=" * 74)
print("=== ДОХОДИМОСТЬ ДО БИТРИКСА ПО ПАСПОРТУ ===")
print("   компаний всего: %5d, лидов: %4d, доехало в Битрикс: %3d"
      % (sum(всего.values()), sum(лид_класс.values()), sum(бит_класс.values())))
