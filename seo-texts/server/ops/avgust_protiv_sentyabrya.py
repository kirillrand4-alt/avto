# -*- coding: utf-8 -*-
"""Август против сентября: письма Meyer и ответы на них, помесячно.

Ответы считаем ПО ПИСЬМУ, а не по дате ответа: письмо августа, на которое
ответили в сентябре, — заслуга августа. Иначе месяцы ведут чужие ответы.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
МЕСЯЦЫ = ("2026-08", "2026-09")
store = Store(r"C:\sender\sender.db")
усл_m = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)

блоки = []
with store._lock:
    c = store._conn
    for м in МЕСЯЦЫ:
        писем = c.execute(
            "SELECT COUNT(*) FROM messages m WHERE m.status='sent' "
            "  AND substr(m.sent_at,1,7)=? AND (%s)" % усл_m, (м,)).fetchone()[0]
        компаний = c.execute(
            "SELECT COUNT(DISTINCT r.inn) FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND substr(m.sent_at,1,7)=? AND (%s)"
            % усл_m, (м,)).fetchone()[0]
        # ответы, привязанные к письмам ЭТОГО месяца
        строки = c.execute(
            "SELECT e.event_type, e.detail_json, e.event_ts, e.recipient_id "
            "  FROM events e JOIN messages m ON e.message_id = m.id "
            " WHERE e.event_type IN ('reply','reply_auto') "
            "   AND m.status='sent' AND substr(m.sent_at,1,7)=? AND (%s)"
            % усл_m, (м,)).fetchall()
        живые = [с for с in строки if с["event_type"] == "reply"]
        авто = [с for с in строки if с["event_type"] == "reply_auto"]
        кто = {с["recipient_id"] for с in живые}
        метки = Counter()
        когда = Counter()
        for с in живые:
            try:
                д = json.loads(с["detail_json"] or "{}")
            except Exception:                                   # noqa: BLE001
                д = {}
            метки[str(д.get("reply_kind") or "без метки")] += 1
            когда[str(с["event_ts"])[:7]] += 1

        б = ["", "=" * 74, "=== %s ===" % м,
             "   писем отправлено:        %6d" % писем,
             "   компаний охвачено:       %6d" % компаний,
             "",
             "   ЖИВЫХ ответов:           %6d   (%.2f%% от писем)"
             % (len(живые), 100.0 * len(живые) / писем if писем else 0),
             "   из них разных компаний:  %6d" % len(кто),
             "   автоответов (машина):    %6d" % len(авто),
             "",
             "   состав живых ответов:"]
        for к, n in метки.most_common():
            б.append("      %-20s %4d  (%.1f%%)"
                     % (к, n, 100.0 * n / len(живые) if живые else 0))
        б.append("")
        б.append("   когда отвечали: %s"
                 % ", ".join("%s: %d" % (к, n) for к, n in sorted(когда.items())))
        блоки.append("\n".join(б))

    # письма без карточки confirm_review к событию не привяжутся — проверим охват
    всего_живых = c.execute(
        "SELECT COUNT(*) FROM events e WHERE e.event_type='reply' "
        "  AND e.event_ts >= '2026-08-01' AND (%s)"
        % " OR ".join("e.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)).fetchone()[0]

print("\n".join(блоки))
print("")
print("=" * 74)
print("=== СВЕРКА ===")
print("   живых ответов всего по журналу с 01.08: %d" % всего_живых)
print("   (если сумма по месяцам меньше — часть событий не привязана к письму)")
