# -*- coding: utf-8 -*-
"""Улетят ли ещё письма тем, кто уже ответил.

ЧЗОК ответил «не актуально» в 10:30, а карточка #4154 висит approved.
Хёгер просил писать на info@ 18.08, карточка #1766 тоже approved. Смотрим
статус самих писем: если 'skipped' — цепочка остановлена, если 'scheduled'
— письмо ещё в очереди на вылет.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for рид in (1766, 4154):
    р = c.execute("SELECT cr.id, cr.status, cr.message_id, cr.subject, "
                  "       r.email, r.inn, r.company_name "
                  "  FROM confirm_reviews cr "
                  "  JOIN recipients r ON r.id=cr.recipient_id "
                  " WHERE cr.id=?", (рид,)).fetchone()
    if not р:
        print("#%s — карточки нет" % рид)
        continue
    м = c.execute("SELECT status, sent_at, last_error FROM messages WHERE id=?",
                  (р["message_id"],)).fetchone() if р["message_id"] else None
    print("#%-6s карточка=%-10s %-28s %s"
          % (р["id"], р["status"], р["email"], str(р["company_name"] or "")[:30]))
    print("        письмо %s: %s"
          % (р["message_id"],
             ("статус=%s, отправлено=%s, ошибка=%s"
              % (м["status"], str(м["sent_at"] or "-")[:16],
                 str(м["last_error"] or "-")[:70])) if м else "нет строки"))

print("\n=== СКОЛЬКО ОДОБРЕННЫХ ПИСЕМ АДРЕСАТАМ, КОТОРЫЕ УЖЕ ОТВЕТИЛИ ===")
строки = c.execute(
    "SELECT cr.id, cr.status, cr.message_id, r.email, m.status mst "
    "  FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.status IN ('approved','pending') "
    "   AND EXISTS (SELECT 1 FROM events e WHERE e.recipient_id=r.id "
    "                 AND e.event_type='reply')").fetchall()
print("  карточек: %d" % len(строки))
свод = {}
for р in строки:
    свод[str(р["mst"])] = свод.get(str(р["mst"]), 0) + 1
for к, н in sorted(свод.items(), key=lambda x: -x[1]):
    метка = " ← ЭТИ УЛЕТЯТ" if к in ("scheduled", "queued") else ""
    print("    письмо в статусе %-12s %d%s" % (к, н, метка))
for р in строки[:12]:
    print("      #%-6s %-28s письмо %s" % (р["id"], р["email"], р["mst"]))
