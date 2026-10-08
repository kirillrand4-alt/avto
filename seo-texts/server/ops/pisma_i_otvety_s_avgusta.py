# -*- coding: utf-8 -*-
"""Письма Meyer с 1 августа и ответы на них: живые отдельно от машинных.

Живой ответ — событие 'reply' (человек написал сам). 'reply_auto' —
автоответ почтовика или отпуск, человека за ним нет. Внутри живых
показываем состав по метке классификатора.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

С = "2026-08-01"
МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
store = Store(r"C:\sender\sender.db")
усл_m = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)
усл_e = " OR ".join("e.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)

with store._lock:
    c = store._conn
    писем = c.execute(
        "SELECT COUNT(*) FROM messages m WHERE m.status='sent' "
        "  AND m.sent_at >= ? AND (%s)" % усл_m, (С,)).fetchone()[0]
    компаний = c.execute(
        "SELECT COUNT(DISTINCT r.inn) FROM messages m "
        "  JOIN recipients r ON m.recipient_id = r.id "
        " WHERE m.status='sent' AND m.sent_at >= ? AND (%s)" % усл_m,
        (С,)).fetchone()[0]

    живые = c.execute(
        "SELECT COUNT(*) FROM events e WHERE e.event_type='reply' "
        "  AND e.event_ts >= ? AND (%s)" % усл_e, (С,)).fetchone()[0]
    машинные = c.execute(
        "SELECT COUNT(*) FROM events e WHERE e.event_type='reply_auto' "
        "  AND e.event_ts >= ? AND (%s)" % усл_e, (С,)).fetchone()[0]
    компаний_отв = c.execute(
        "SELECT COUNT(DISTINCT e.recipient_id) FROM events e "
        " WHERE e.event_type='reply' AND e.event_ts >= ? AND (%s)" % усл_e,
        (С,)).fetchone()[0]

    print("--- живые ответы по месяцам ---")
    for р in c.execute(
            "SELECT substr(e.event_ts,1,7) м, COUNT(*) n FROM events e "
            " WHERE e.event_type='reply' AND e.event_ts >= ? AND (%s) "
            " GROUP BY 1 ORDER BY 1" % усл_e, (С,)):
        print("   %s  %4d" % (р["м"], р["n"]))

    print("")
    print("--- состав живых ответов по метке ---")
    import json
    метки = Counter()
    for р in c.execute(
            "SELECT e.detail_json FROM events e WHERE e.event_type='reply' "
            "  AND e.event_ts >= ? AND (%s)" % усл_e, (С,)):
        try:
            д = json.loads(р["detail_json"] or "{}")
        except Exception:                                       # noqa: BLE001
            д = {}
        метки[str(д.get("reply_kind") or "без метки")] += 1
    for к, n in метки.most_common():
        print("   %-22s %4d  (%.1f%%)"
              % (к, n, 100.0 * n / живые if живые else 0))

print("")
print("=" * 74)
print("=== MEYER С 1 АВГУСТА ===")
print("   писем отправлено:        %6d" % писем)
print("   компаний охвачено:       %6d" % компаний)
print("")
print("   ЖИВЫХ ответов:           %6d   (%.2f%% от писем)"
      % (живые, 100.0 * живые / писем if писем else 0))
print("   из них разных компаний:  %6d" % компаний_отв)
print("   автоответов (машина):    %6d" % машинные)
