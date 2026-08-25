# -*- coding: utf-8 -*-
"""Вернуть в очередь ОТПРАВКИ карточки, подтверждённые вчера.

Вчера они были approved, я сбросил их в pending из-за устаревшего правила 2
линзы — то есть заставил оператора подтверждать заново то, что он уже
подтвердил. Владелец 25.08: «верни в очередь отправки».

Возвращаем и карточку (approved), и письмо (scheduled), иначе карточка
одобрена, а письмо лежит в pending_review и автоотправка его не видит.
"""
import sqlite3
import sys

ДЕЛАТЬ = "--вернуть" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

цель = c.execute(
    "SELECT cr.id, cr.message_id, COALESCE(m.status,'нет письма') mst "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.status='pending' AND cr.reason LIKE '%устаревшему правилу 2%'"
    ).fetchall()
print("карточек к возврату: %d" % len(цель))
from collections import Counter
for к, н in Counter(р["mst"] for р in цель).most_common():
    print("  письмо %-18s %d" % (к, н))

if not ДЕЛАТЬ:
    print("\nсухой прогон. Вернуть — --вернуть")
    raise SystemExit(0)

ид = [р["id"] for р in цель]
письма = [р["message_id"] for р in цель if р["message_id"]]
места = ",".join("?" * len(ид))
c.execute(
    "UPDATE confirm_reviews SET status='approved', "
    "       decided_by='возврат подтверждения (владелец 25.08)', "
    "       decided_at=datetime('now'), "
    "       reason='подтверждено 24.08, снято мной ошибочно, возвращено', "
    "       updated_at=datetime('now') WHERE id IN (%s)" % места, ид)
if письма:
    м2 = ",".join("?" * len(письма))
    c.execute(
        "UPDATE messages SET status='scheduled', last_error=NULL, "
        "       scheduled_at=datetime('now'), updated_at=datetime('now') "
        " WHERE id IN (%s) AND status NOT IN ('sent','failed')" % м2, письма)
c.commit()
print("\nвозвращено: %d карточек, писем в scheduled: %d" % (len(ид), len(письма)))
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   " GROUP BY status ORDER BY n DESC"):
    print("  карточки %-12s %5d" % (р["status"], р["n"]))
for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                   " WHERE status NOT IN ('sent','skipped','failed') "
                   " GROUP BY status"):
    print("  письма   %-12s %5d" % (р["status"], р["n"]))
