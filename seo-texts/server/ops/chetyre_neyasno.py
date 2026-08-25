# -*- coding: utf-8 -*-
"""Найти четыре «неясно», которых не видит фильтр, и снять их."""
import sqlite3
import sys

СНЯТЬ = "--снять" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

print("=== ПИСЬМА В scheduled И ИХ ВЕРДИКТЫ ===")
цель = []
for р in c.execute(
        "SELECT m.id mid, m.status mst, r.email, r.company_name, cr.id crid, "
        "       cr.status crst FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
        " WHERE m.status='scheduled'"):
    адрес = str(р["email"] or "")
    в = c.execute("SELECT verdict FROM addr_probe WHERE email=? OR lower(email)=?",
                  (адрес, адрес.strip().lower())).fetchone()
    вердикт = в["verdict"] if в else "ВЕРДИКТА НЕТ"
    if вердикт in ("неясно", "нет ящика", "нет MX", "отказ пробе",
                   "ВЕРДИКТА НЕТ"):
        цель.append((р, вердикт))
        print("  письмо #%-6s карточка #%-6s %-30s %-14s (карточка %s)"
              % (р["mid"], р["crid"], адрес[:30], вердикт, р["crst"]))
print("  ---- под снятие: %d" % len(цель))

if not СНЯТЬ:
    print("\nсухой прогон. Снять — --снять")
else:
    for р, в in цель:
        c.execute("UPDATE messages SET status='skipped', last_error=?, "
                  "  updated_at=datetime('now') WHERE id=?",
                  ("проба: %s" % в, р["mid"]))
        if р["crid"]:
            c.execute("UPDATE confirm_reviews SET status='skipped', "
                      "  decided_by='вердикт пробы (владелец 25.08)', "
                      "  decided_at=datetime('now'), reason=?, "
                      "  updated_at=datetime('now') WHERE id=?",
                      ("адрес: %s" % в, р["crid"]))
    c.commit()
    print("\nснято: %d" % len(цель))

print("\n=== ОТКУДА ПИСЬМА В ОЧЕРЕДИ ПОДТВЕРЖДЕНИЯ (pending) ===")
for р in c.execute(
        "SELECT substr(cr.created_at,1,10) д, COUNT(*) n FROM confirm_reviews cr "
        " WHERE cr.status='pending' GROUP BY д ORDER BY д DESC"):
    print("  создано %s: %d" % (р["д"], р["n"]))

print("\n=== СКОЛЬКО ИЗ НИХ ПРОШЛО ЛИНЗУ (по причине снятия соседей) ===")
н = c.execute("SELECT COUNT(*) n FROM confirm_reviews WHERE status='pending'"
              ).fetchone()["n"]
print("  всего pending: %d" % н)
