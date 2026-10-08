# -*- coding: utf-8 -*-
"""Чьи лиды доехали до Битрикса: Meyer, компрессорные или оба писали.

Я брал ВСЕ карточки, когда-либо заходившие в Битрикс, и пересекал их с
компаниями, которым писал Meyer. Если компании писали оба направления,
сделка могла вырасти из компрессорного письма, а зачлась Meyer. Проверяем
по ящику, с которого пришёл ответ, и по ящикам отправки.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")


def мейер(ящик) -> bool:
    s = str(ящик or "")
    return any(s.endswith(д) for д in МЕЙЕР)


store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    в_битриксе = {р["lead_id"] for р in c.execute(
        "SELECT DISTINCT lead_id FROM lead_events WHERE to_status='in_bitrix'")}
    for р in c.execute("SELECT id FROM leads WHERE status='in_bitrix'"):
        в_битриксе.add(р["id"])
    print("карточек, заходивших в Битрикс: %d" % len(в_битриксе))

    свод = Counter()
    строки = []
    for лид in sorted(в_битриксе):
        л = c.execute("SELECT id, inn, email, company_name, recipient_id "
                      "  FROM leads WHERE id=?", (лид,)).fetchone()
        if not л:
            continue
        # ящик, с которого пришёл ОТВЕТ (по нему лид и завёлся)
        ответы = [р["mailbox_id"] for р in c.execute(
            "SELECT e.mailbox_id FROM events e "
            " WHERE e.event_type IN ('reply','reply_auto') "
            "   AND (e.recipient_id = ? OR e.recipient_id IN "
            "        (SELECT id FROM recipients WHERE inn = ?))"
            " ORDER BY e.id", (л["recipient_id"], л["inn"]))]
        # ящики, которыми вообще писали этой компании
        письма = [р["mailbox_id"] for р in c.execute(
            "SELECT DISTINCT m.mailbox_id FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND r.inn = ?", (л["inn"],))]
        м_отв = any(мейер(x) for x in ответы)
        к_отв = any(x and not мейер(x) for x in ответы)
        м_пис = any(мейер(x) for x in письма)
        к_пис = any(x and not мейер(x) for x in письма)
        если = ("ответ Meyer" if м_отв and not к_отв else
                "ответ КЦ" if к_отв and not м_отв else
                "ответы с обоих" if м_отв and к_отв else
                ("ответа нет; писал Meyer" if м_пис and not к_пис else
                 "ответа нет; писал КЦ" if к_пис and not м_пис else
                 "ответа нет; писали оба" if м_пис and к_пис else "следов нет"))
        свод[если] += 1
        строки.append("   лид %-5s %-30s %s"
                      % (л["id"], str(л["company_name"])[:30], если))

print("")
print("--- по каждой карточке ---")
print("\n".join(строки))
print("")
print("=" * 74)
print("=== ЧЬИ СДЕЛКИ В БИТРИКСЕ ===")
for к, n in свод.most_common():
    print("   %-28s %3d" % (к, n))
