# -*- coding: utf-8 -*-
"""Писали ли мы им на самом деле: строка в получателях против отправки.

Запись в recipients появляется при загрузке партии — это «завели», а не
«написали». Письмо есть только если в messages лежит строка со статусом
sent. И проверять надо по ИНН тоже: компании могли писать на ДРУГОЙ адрес.
"""
import io
import json
import os
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
store = Store(r"C:\sender\sender.db")
строки = []
for ф in ("pasporta_rf.json", "pasporta_by.json"):
    п = os.path.join(r"C:\sender\server\ops", ф)
    if os.path.exists(п):
        строки.extend(json.load(io.open(п, encoding="utf-8")))

инны, почты = set(), set()
for с in строки:
    ид = str(с["ид"])
    ц = "".join(x for x in ид if x.isdigit())
    if ид.isdigit() and len(ц) in (10, 12):
        инны.add(ц)
    if с["почта"]:
        почты.add(с["почта"])

усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)
итог = {}
with store._lock:
    c = store._conn

    def порциями(значения, запрос):
        всего = 0
        сп = list(значения)
        for н in range(0, len(сп), 400):
            куски = сп[н:н + 400]
            м = ",".join("?" * len(куски))
            всего += c.execute(запрос.replace("{IN}", м),
                               куски).fetchone()[0]
        return всего

    итог["адрес заведён в получателях"] = порциями(
        почты, "SELECT COUNT(DISTINCT lower(email)) FROM recipients "
               " WHERE lower(email) IN ({IN})")
    итог["на этот адрес письмо УХОДИЛО"] = порциями(
        почты, "SELECT COUNT(DISTINCT lower(r.email)) FROM messages m "
               "  JOIN recipients r ON m.recipient_id = r.id "
               " WHERE m.status='sent' AND lower(r.email) IN ({IN})")
    итог["на этот адрес уходило с ящика Meyer"] = порциями(
        почты, "SELECT COUNT(DISTINCT lower(r.email)) FROM messages m "
               "  JOIN recipients r ON m.recipient_id = r.id "
               " WHERE m.status='sent' AND (" + усл + ") "
               "   AND lower(r.email) IN ({IN})")
    итог["ИНН заведён в получателях"] = порциями(
        инны, "SELECT COUNT(DISTINCT inn) FROM recipients WHERE inn IN ({IN})")
    итог["компании УЖЕ писали (на любой адрес)"] = порциями(
        инны, "SELECT COUNT(DISTINCT r.inn) FROM messages m "
              "  JOIN recipients r ON m.recipient_id = r.id "
              " WHERE m.status='sent' AND r.inn IN ({IN})")
    итог["компании писали с ящика Meyer"] = порциями(
        инны, "SELECT COUNT(DISTINCT r.inn) FROM messages m "
              "  JOIN recipients r ON m.recipient_id = r.id "
              " WHERE m.status='sent' AND (" + усл + ") AND r.inn IN ({IN})")
    итог["компании отвечали живым ответом"] = порциями(
        инны, "SELECT COUNT(DISTINCT r.inn) FROM events e "
              "  JOIN recipients r ON e.recipient_id = r.id "
              " WHERE e.event_type='reply' AND r.inn IN ({IN})")

print("   %-44s %6s" % ("", "штук"))
for к in ("адрес заведён в получателях", "на этот адрес письмо УХОДИЛО",
          "на этот адрес уходило с ящика Meyer", "ИНН заведён в получателях",
          "компании УЖЕ писали (на любой адрес)",
          "компании писали с ящика Meyer", "компании отвечали живым ответом"):
    print("   %-44s %6d" % (к, итог[к]))
print("")
print("=" * 74)
print("=== ЗАВЕДЕНЫ ПРОТИВ НАПИСАНЫ ===")
print("   адресов в книгах: %d, компаний по ИНН: %d" % (len(почты), len(инны)))
print("   по-настоящему новых адресов: %d"
      % (len(почты) - итог["на этот адрес письмо УХОДИЛО"]))
print("   компаний, которым ни разу не писали: %d"
      % (len(инны) - итог["компании УЖЕ писали (на любой адрес)"]))
