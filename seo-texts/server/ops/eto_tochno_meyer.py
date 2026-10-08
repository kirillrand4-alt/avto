# -*- coding: utf-8 -*-
"""Проверка фильтра: всё ли в счёте — направление Meyer.

Я считал по ящикам отправки (девять доменов Meyer). Это не то же самое,
что направление письма: с ящика Meyer могло уйти компрессорное письмо.
Сверяем по кампании и по letter_division из карточки письма.
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

по_кампаниям = Counter()
по_направлению = Counter()
смесь = Counter()
with store._lock:
    c = store._conn
    имена = {р["id"]: р["name"] for р in c.execute("SELECT id, name FROM campaigns")}
    for р in c.execute(
            "SELECT m.campaign_id, cr.panel_json FROM messages m "
            "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
            " WHERE m.status='sent' AND m.sent_at >= '2026-08-01' AND (%s)" % усл):
        по_кампаниям[р["campaign_id"]] += 1
        нап = "(карточки нет)"
        if р["panel_json"]:
            try:
                д = json.loads(р["panel_json"])
                нап = str(д.get("letter_division") or "(не указано)")
            except Exception:                                   # noqa: BLE001
                нап = "(карточка битая)"
        по_направлению[нап] += 1
        смесь[(р["campaign_id"], нап)] += 1

    # были ли письма Meyer с ЧУЖИХ ящиков
    чужие = c.execute(
        "SELECT COUNT(*) FROM messages m WHERE m.status='sent' "
        "  AND m.sent_at >= '2026-08-01' AND NOT (%s)" % усл).fetchone()[0]

print("--- кампании в моём счёте ---")
for к, n in по_кампаниям.most_common():
    print("   кампания %-4s %-32s %5d" % (к, str(имена.get(к))[:32], n))

print("")
print("--- направление письма по карточке (letter_division) ---")
for к, n in по_направлению.most_common():
    print("   %-18s %5d" % (к, n))

print("")
print("--- где направление не meyer ---")
for (к, нап), n in смесь.most_common():
    if нап in ("meyer",):
        continue
    print("   кампания %-4s %-28s %-16s %4d"
          % (к, str(имена.get(к))[:28], нап, n))

print("")
print("=" * 74)
print("=== ЭТО ТОЧНО MEYER? ===")
print("   писем в счёте (с ящиков Meyer):      %5d" % sum(по_кампаниям.values()))
print("   из них направление meyer:            %5d" % по_направлению.get("meyer", 0))
print("   писем с ДРУГИХ ящиков за тот же срок: %5d" % чужие)
