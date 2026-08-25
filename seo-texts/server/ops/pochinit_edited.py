# -*- coding: utf-8 -*-
"""Закрыть карточки edited, чьё письмо давно отправлено.

Оператор правил текст, письмо ушло, а статус карточки остался 'edited'.
Виджет «ждут подтверждения» считает такие карточки ждущими: владелец видел
96 при пяти настоящих, а до этого 434 при 343. Приводим статус в
соответствие с фактом: письмо отправлено — карточка 'sent'.
"""
import sqlite3
import sys

ДЕЛАТЬ = "--чинить" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

цель = c.execute(
    "SELECT cr.id, cr.created_at, m.sent_at FROM confirm_reviews cr "
    "  JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.status='edited' AND m.status='sent'").fetchall()
print("карточек edited с отправленным письмом: %d" % len(цель))
for р in цель[:5]:
    print("  #%-6s создана %s, письмо ушло %s"
          % (р["id"], str(р["created_at"])[:16], str(р["sent_at"])[:16]))

прочие = c.execute(
    "SELECT cr.id, COALESCE(m.status,'нет письма') mst FROM confirm_reviews cr "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.status='edited' AND COALESCE(m.status,'') <> 'sent'").fetchall()
if прочие:
    print("\nостальные edited (их не трогаем):")
    for р in прочие:
        print("  #%-6s письмо %s" % (р["id"], р["mst"]))

if not ДЕЛАТЬ:
    print("\nсухой прогон. Чинить — --чинить")
    raise SystemExit(0)

ид = [р["id"] for р in цель]
if ид:
    места = ",".join("?" * len(ид))
    c.execute(
        "UPDATE confirm_reviews SET status='sent', "
        "  reason=COALESCE(NULLIF(reason,''),'закрыто: письмо отправлено'), "
        "  updated_at=datetime('now') WHERE id IN (%s)" % места, ид)
    c.commit()
print("\nзакрыто карточек: %d" % len(ид))
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   " GROUP BY status ORDER BY n DESC"):
    print("  %-12s %5d" % (р["status"], р["n"]))
