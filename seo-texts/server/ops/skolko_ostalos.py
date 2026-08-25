# -*- coding: utf-8 -*-
"""Сколько писем реально осталось в очереди и во что обойдётся линза."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

print("=== КАРТОЧКИ ===")
всего_живых = 0
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   " GROUP BY status ORDER BY n DESC"):
    if р["status"] in ("pending", "approved", "edited"):
        всего_живых += р["n"]
    print("  %-14s %5d" % (р["status"], р["n"]))
print("  ---- живых (pending+approved+edited): %d" % всего_живых)

print("\n=== ПИСЬМА ===")
for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                   " WHERE status NOT IN ('sent','skipped','failed') "
                   " GROUP BY status ORDER BY n DESC"):
    print("  %-16s %5d" % (р["status"], р["n"]))

print("\n=== ЖИВЫЕ КАРТОЧКИ ПО ДАТЕ И НАПРАВЛЕНИЮ ===")
for р in c.execute(
        "SELECT substr(cr.created_at,1,10) д, "
        "       CASE WHEN m.campaign_id=11 THEN 'meyer' ELSE 'kc' END напр, "
        "       cr.status, COUNT(*) n FROM confirm_reviews cr "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status IN ('pending','approved','edited') "
        " GROUP BY д, напр, cr.status ORDER BY д DESC, n DESC"):
    print("  %s  %-6s %-10s %5d" % (р["д"], р["напр"], р["status"], р["n"]))

print("\n=== ЦЕНА ЛИНЗЫ ПО ЭТОМУ ОБЪЁМУ ===")
н = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews "
    " WHERE status IN ('pending','approved','edited') "
    "   AND COALESCE(body,'')<>''").fetchone()["n"]
print("  писем с текстом: %d" % н)
print("  пачками по восемь: $%.2f" % (н * 0.0051))
print("  (замер 24.08: $0.0051 за письмо на пачках)")
