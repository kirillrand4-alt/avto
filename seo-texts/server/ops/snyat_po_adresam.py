# -*- coding: utf-8 -*-
"""Снять письма по вердикту пробы: приговор, «неясно», непроверенные.

Владелец 25.08: «6 неясно, 3 непроверенных, 29 писем на приговорённые
адреса — снимай». Берём и очередь отправки, и одобренные карточки, иначе
приговорённые доедут до отправки позже.
"""
import sqlite3
import sys
from collections import Counter

СНЯТЬ = "--снять" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

цель = c.execute(
    "SELECT cr.id, cr.status, m.id mid, COALESCE(m.status,'-') mst, "
    "       r.email, r.company_name, COALESCE(p.verdict,'ВЕРДИКТА НЕТ') в "
    "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
    # ЦЕЛИМСЯ В ПИСЬМО, А НЕ В КАРТОЧКУ. Первая редакция фильтровала по
    # cr.status IN ('approved','pending') и поймала 6 из 38: часть писем висит
    # на карточках в статусе 'edited' (оператор правил текст), и они уходят
    # так же, как одобренные.
    " WHERE m.status NOT IN ('sent','skipped','failed') "
    "   AND (p.verdict IN ('нет ящика','нет MX','неясно','отказ пробе') "
    "        OR p.email IS NULL)").fetchall()

print("под снятие: %d" % len(цель))
for к, н in Counter(р["в"] for р in цель).most_common():
    print("  %-18s %d" % (к, н))
print("\nпримеры:")
for р in цель[:10]:
    print("  #%-6s %-32s %-14s письмо %s"
          % (р["id"], str(р["email"])[:32], р["в"], р["mst"]))

if not СНЯТЬ:
    print("\nсухой прогон. Снять — --снять")
    raise SystemExit(0)

снято = 0
for р in цель:
    c.execute("UPDATE confirm_reviews SET status='skipped', "
              "  decided_by='вердикт пробы (владелец 25.08)', "
              "  decided_at=datetime('now'), reason=?, "
              "  updated_at=datetime('now') WHERE id=?",
              ("адрес: %s" % р["в"], р["id"]))
    if р["mid"]:
        c.execute("UPDATE messages SET status='skipped', last_error=?, "
                  "  updated_at=datetime('now') "
                  " WHERE id=? AND status NOT IN ('sent','failed')",
                  ("проба: %s" % р["в"], р["mid"]))
    снято += 1
c.commit()
print("\nснято: %d" % снято)
print("\n=== ЧТО ОСТАЛОСЬ В ОТПРАВКЕ ===")
for р in c.execute(
        "SELECT COALESCE(p.verdict,'ВЕРДИКТА НЕТ') в, COUNT(*) n "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
        " WHERE m.status='scheduled' GROUP BY в ORDER BY n DESC"):
    print("  %-18s %d" % (р["в"], р["n"]))
