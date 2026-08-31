# -*- coding: utf-8 -*-
"""Кто одобрил 21 письмо кампании 11 за последний час и ушли ли они."""
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
строки = list(c.execute(
    "SELECT cr.id, cr.status, cr.decided_by, cr.decided_at, cr.message_id,"
    "       m.status ms, m.sent_at, m.scheduled_at, cr.email"
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id"
    " WHERE cr.campaign_id=11 AND cr.status='approved'"
    "   AND cr.created_at >= datetime('now','-3 hour')"
    " ORDER BY cr.id"))
print("одобренных за 3 часа: %d" % len(строки))
кем = {}
for s in строки:
    кем[str(s["decided_by"] or "(не записан)")] = кем.get(
        str(s["decided_by"] or "(не записан)"), 0) + 1
print("кем одобрены: %s" % кем)
ушло = sum(1 for s in строки if s["sent_at"])
запланировано = sum(1 for s in строки if s["scheduled_at"] and not s["sent_at"])
print("реально отправлено: %d; поставлено в расписание: %d" % (ушло, запланировано))
for s in строки[:8]:
    print("   %d %-22s кем=%-12s статус письма=%-14s sent=%s"
          % (s["id"], (s["email"] or "")[:22], str(s["decided_by"] or "")[:12],
             str(s["ms"] or ""), s["sent_at"]))
print("\n=== ЗА СУТКИ ПО ВСЕМ КАМПАНИЯМ ===")
for r in c.execute("SELECT campaign_id, COUNT(*) n, SUM(CASE WHEN sent_at IS NOT NULL"
                   " THEN 1 ELSE 0 END) ушло FROM messages"
                   " WHERE created_at >= datetime('now','-1 day')"
                   " GROUP BY campaign_id"):
    print("   кампания %-4s писем %5d, отправлено %5d" % (r[0], r[1], r[2] or 0))
c.close()
print("\n=== ИТОГ ===")
print("одобрено за 3 часа %d, из них ушло %d" % (len(строки), ушло))
