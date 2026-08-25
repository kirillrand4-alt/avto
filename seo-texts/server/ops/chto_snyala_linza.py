# -*- coding: utf-8 -*-
"""Полная опись писем, снятых линзой: что из этого моя ошибка, а что дело.

Правило 2 линзы («строка отказа запрещена») — устаревшая редакция 14.08,
она про Meyer; для КЦ строка отказа — обязательный канон, на письма с ней
приходили живые ответы. Всё, что снято по нему, снято мной зря. Туда же
«ответ линзы не разобрался» — это сбой разбора, а не вердикт.

Отдельно проверяем адрес: возвращать письмо на приговорённый ящик нельзя.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
try:
    приговор = {р[0].strip().lower(): р[1] for р in c.execute(
        "SELECT email, verdict FROM addr_probe")}
except Exception:  # noqa: BLE001
    приговор = {}
ПЛОХО = ("нет ящика", "нет MX")

ряды = c.execute(
    "SELECT cr.id, cr.status st, COALESCE(m.status,'нет письма') ms, "
    "       COALESCE(NULLIF(m.last_error,''), cr.reason,'') почему, "
    "       LOWER(COALESCE(r.email,'')) адрес, cr.message_id mid "
    "  FROM confirm_reviews cr "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE (m.status='skipped' OR cr.status='skipped') "
    "   AND (COALESCE(m.last_error,'') LIKE '%линза%' "
    "        OR COALESCE(cr.reason,'') LIKE '%линза%')").fetchall()
print("снято линзой всего: %d" % len(ряды))


def разряд(п):
    п = п.lower()
    if "не разобрался" in п:
        return "сбой разбора линзы — не вердикт"
    if "правило 2" in п:
        return "правило 2: строка отказа — УСТАРЕВШЕЕ"
    for н in ("19в", "правило 11", "правило 1", "правило 3", "правило 4",
              "правило 9"):
        if н in п:
            return "правило %s" % н.replace("правило ", "")
    return "прочее: " + п[:44]


разряды = Counter(разряд(р["почему"]) for р in ряды)
for к, н in разряды.most_common(14):
    print("   %-52s %5d" % (к, н))

вернуть = [р for р in ряды
           if разряд(р["почему"]).startswith(("правило 2:", "сбой разбора"))]
живой_адрес = [р for р in вернуть
               if приговор.get(р["адрес"], "") not in ПЛОХО]
print("\nмоей ошибкой снято: %d, из них адрес не приговорён: %d"
      % (len(вернуть), len(живой_адрес)))
print("состояние этих карточек сейчас:")
for к, н in Counter("карта %s / письмо %s" % (р["st"], р["ms"])
                    for р in живой_адрес).most_common():
    print("   %-40s %5d" % (к, н))
