# -*- coding: utf-8 -*-
"""Кто на самом деле отвечал: доля ответов по роли адреса, куда писали.

Роль берём из обогащения (enrich.emails.role) по паре ИНН+адрес, а где
её нет — по приставке самого ящика. Считаем письма Meyer с 1 августа.
"""
import os
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
ПРИСТАВКИ = [
    (r"^(kachestv|qa|qc|lab)", "качество/лаборатория"),
    (r"^(tehnolog|technolog)", "технолог"),
    (r"^(proizvod|production)", "производство"),
    (r"^(glavinzh|ginzh|inzh|engineer|tech|tehn|cto)", "гл.инженер/техдир"),
    (r"^(zakup|snab|postavk|tender|purchase)", "снабжение/закупки"),
    (r"^(sale|prodazh|sbyt|commerc|kommerc|opt)", "продажи"),
    (r"^(director|dir|ceo|gendir|rukovod)", "директор"),
    (r"^(info|office|mail|post|priem|reception|sekret|kontakt)", "общий/приёмная"),
    (r"^(buh|account|finans)", "бухгалтерия"),
    (r"^(hr|kadr|personal)", "кадры"),
]
store = Store(r"C:\sender\sender.db")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)

роли_обог = {}
if os.path.exists(r"C:\sender\enrich.db"):
    cx = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True)
    for инн, адрес, роль in cx.execute(
            "SELECT inn, lower(email), role FROM emails WHERE COALESCE(role,'')<>''"):
        роли_обог[(str(инн), str(адрес))] = str(роль)
    cx.close()


def роль_адреса(инн, адрес):
    р = роли_обог.get((str(инн or ""), адрес))
    if р:
        return р
    лок = адрес.split("@")[0]
    for шаб, имя in ПРИСТАВКИ:
        if re.match(шаб, лок):
            return имя
    return "именной/прочий"


писем, ответов = Counter(), Counter()
with store._lock:
    c = store._conn
    ответившие = {р["mid"] for р in c.execute(
        "SELECT DISTINCT e.message_id mid FROM events e "
        " WHERE e.event_type='reply' AND e.message_id IS NOT NULL")}
    for р in c.execute(
            "SELECT m.id, r.inn, lower(r.email) email FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND m.sent_at >= '2026-08-01' AND (%s)" % усл):
        роль = роль_адреса(р["inn"], р["email"])
        писем[роль] += 1
        if р["id"] in ответившие:
            ответов[роль] += 1

print("   %-26s %7s %8s %8s" % ("роль адреса", "писем", "ответов", "доля"))
строки = []
for роль, n in писем.most_common():
    о = ответов.get(роль, 0)
    строки.append((100.0 * о / n if n else 0, роль, n, о))
for доля, роль, n, о in sorted(строки, key=lambda x: -x[0]):
    если = "" if n >= 50 else "   (мало писем)"
    print("   %-26s %7d %8d %7.2f%%%s" % (роль[:26], n, о, доля, если))
print("")
print("=" * 74)
print("=== КТО ОТВЕЧАЛ, ПО РОЛИ АДРЕСА ===")
print("   всего писем %d, ответов %d (%.2f%%)"
      % (sum(писем.values()), sum(ответов.values()),
         100.0 * sum(ответов.values()) / sum(писем.values())))
