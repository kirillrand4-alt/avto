# -*- coding: utf-8 -*-
"""Откуда расхождение 6306 против 6332: двойные карточки на одно письмо."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
store = Store(r"C:\sender\sender.db")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)
with store._lock:
    c = store._conn
    чисто = c.execute("SELECT COUNT(*) FROM messages m WHERE m.status='sent' "
                      "  AND m.sent_at >= '2026-08-01' AND (%s)" % усл).fetchone()[0]
    с_джойном = c.execute(
        "SELECT COUNT(*) FROM messages m "
        "  LEFT JOIN confirm_reviews cr ON cr.message_id = m.id "
        " WHERE m.status='sent' AND m.sent_at >= '2026-08-01' AND (%s)"
        % усл).fetchone()[0]
    дубли = c.execute(
        "SELECT COUNT(*) FROM (SELECT cr.message_id, COUNT(*) n "
        "  FROM confirm_reviews cr JOIN messages m ON cr.message_id = m.id "
        " WHERE m.status='sent' AND m.sent_at >= '2026-08-01' AND (%s) "
        " GROUP BY 1 HAVING n > 1)" % усл).fetchone()[0]
print("писем без джойна:            %5d" % чисто)
print("строк с LEFT JOIN карточек:  %5d" % с_джойном)
print("писем с двумя карточками:    %5d" % дубли)
print("")
print("=" * 74)
print("=== ДУБЛИ КАРТОЧЕК ===")
