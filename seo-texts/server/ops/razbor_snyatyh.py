# -*- coding: utf-8 -*-
"""Из-за чего 631 письмо снято заслоном и 110 упало с ошибкой."""
import re
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row


def свернуть(т):
    """Свести сообщение об ошибке к классу: убрать адреса, id, цифры."""
    т = str(т or "").strip()
    if not т:
        return "(пусто)"
    т = re.sub(r"[\w.\-]+@[\w.\-]+", "<адрес>", т)
    т = re.sub(r"\b\d[\d.\-:]{3,}\b", "<число>", т)
    т = re.sub(r"\s+", " ", т)
    return т[:110]


print("=== SKIPPED: ПРИЧИНА ИЗ КАРТОЧКИ ===")
skip = list(c.execute(
    "SELECT cr.id, cr.campaign_id, cr.reason, m.last_error, m.status,"
    "       substr(cr.created_at,1,10) д, cr.email"
    "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id"
    " WHERE cr.status IN ('approved','edited') AND m.status='skipped'"))
пр = Counter(свернуть(r["reason"]) for r in skip)
for п, n in пр.most_common(12):
    print("   %5d  %s" % (n, п))
print("   всего skipped: %d" % len(skip))

print("\n=== SKIPPED: ЧТО НАПИСАНО В last_error ПИСЬМА ===")
ош = Counter(свернуть(r["last_error"]) for r in skip)
for п, n in ош.most_common(12):
    print("   %5d  %s" % (n, п))

print("\n=== FAILED: ОШИБКА ОТПРАВКИ ===")
fail = list(c.execute(
    "SELECT cr.id, cr.campaign_id, m.last_error, m.attempt_count,"
    "       substr(cr.created_at,1,10) д, cr.email"
    "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id"
    " WHERE cr.status IN ('approved','edited') AND m.status='failed'"))
for п, n in Counter(свернуть(r["last_error"]) for r in fail).most_common(12):
    print("   %5d  %s" % (n, п))
print("   всего failed: %d" % len(fail))

print("\n=== ПО КАМПАНИЯМ И ДАТАМ ===")
for имя, ряды in (("skipped", skip), ("failed", fail)):
    к = Counter("кампания %s" % r["campaign_id"] for r in ряды)
    д = Counter(r["д"] for r in ряды)
    print("   %-8s %s" % (имя, dict(к.most_common(6))))
    print("            даты: %s" % dict(sorted(д.items())[-6:]))

print("\n=== ЧТО ИЗ ЭТОГО МОЖНО ВЕРНУТЬ ===")
# приговор пробы = не вернуть; всё остальное — кандидаты на пересмотр
пробы = {}
for r in c.execute("SELECT email, verdict FROM addr_probe"):
    пробы[str(r["email"] or "").strip().lower()] = str(r["verdict"] or "")
мёртв = ("нет ящика", "нет MX")
свод = Counter()
for имя, ряды in (("skipped", skip), ("failed", fail)):
    for r in ряды:
        а = str(r["email"] or "").strip().lower()
        в = пробы.get(а, "")
        if в in мёртв:
            свод["%s: адрес мёртв — не вернуть" % имя] += 1
        elif в:
            свод["%s: адрес живой (вердикт «%s»)" % (имя, в)] += 1
        else:
            свод["%s: адрес не проверен" % имя] += 1
for к, n in свод.most_common():
    print("   %5d  %s" % (n, к))
c.close()

живых = sum(n for к, n in свод.items() if "живой" in к)
непров = sum(n for к, n in свод.items() if "не проверен" in к)
print("\n=== ИТОГ ===")
print("снято заслоном %d, упало %d; итого %d" % (len(skip), len(fail),
                                                 len(skip) + len(fail)))
print("из них адрес живой: %d, не проверен: %d — вот это и есть запас"
      % (живых, непров))
