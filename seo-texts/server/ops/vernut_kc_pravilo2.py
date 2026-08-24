# -*- coding: utf-8 -*-
"""Вернуть в очередь КЦ-письма, снятые линзой по устаревшему правилу 2.

Линза несёт редакцию 14.08 (строка отказа запрещена всем). Владелец 17.08
уточнил, что решение касалось только Meyer, и для КЦ строка ОБЯЗАТЕЛЬНА —
zashit_kontsovku её дописывает, а в комментарии стоит замер: «на письма с
ней приходили ответы». Значит снятие было ошибкой, и её надо отменить.

Возвращаем в pending, а не в approved: решение об отправке принимает
оператор, а не скрипт, который сам же и ошибся.
"""
import sqlite3
import sys

СНЯТЬ = "--вернуть" in sys.argv or "--vernut" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

цель = c.execute(
    "SELECT cr.id, cr.message_id, m.status mst, r.company_name "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.status='skipped' AND COALESCE(cr.decided_by,'') LIKE '%линза%' "
    "   AND cr.reason LIKE '%правило 2%' "
    "   AND COALESCE(m.campaign_id, 10) <> 11 "
    "   AND COALESCE(m.status,'') <> 'sent'").fetchall()
print("к возврату: %d карточек" % len(цель))
for р in цель[:5]:
    print("  #%-6s %-34s письмо=%s" % (р["id"], str(р["company_name"] or "")[:34],
                                       р["mst"]))
if not СНЯТЬ:
    print("\nсухой прогон. Вернуть — --вернуть")
    raise SystemExit(0)

ид = [р["id"] for р in цель]
письма = [р["message_id"] for р in цель if р["message_id"]]
места = ",".join("?" * len(ид))
c.execute(
    "UPDATE confirm_reviews SET status='pending', decided_at=NULL, "
    "       decided_by=NULL, reason='возврат: снято по устаревшему правилу 2', "
    "       updated_at=datetime('now') WHERE id IN (%s)" % места, ид)
вернули_карточек = c.total_changes
if письма:
    места2 = ",".join("?" * len(письма))
    c.execute(
        "UPDATE messages SET status='pending_review', last_error=NULL, "
        "       updated_at=datetime('now') "
        " WHERE id IN (%s) AND status NOT IN ('sent','failed')" % места2, письма)
c.commit()
print("\nвозвращено карточек: %d" % len(ид))
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   " GROUP BY status ORDER BY n DESC"):
    print("  %-14s %5d" % (р["status"], р["n"]))
