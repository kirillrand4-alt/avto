# -*- coding: utf-8 -*-
"""Те самые 91: карточки в статусе edited, зависшие с 17-19 августа."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   " GROUP BY status ORDER BY n DESC"):
    print("  %-14s %5d" % (р["status"], р["n"]))
p = c.execute("SELECT COUNT(*) n FROM confirm_reviews WHERE status='pending'").fetchone()["n"]
e = c.execute("SELECT COUNT(*) n FROM confirm_reviews WHERE status='edited'").fetchone()["n"]
print("\n  pending %d + edited %d = %d" % (p, e, p + e))

print("\n=== ЧТО С ПИСЬМАМИ ЭТИХ edited ===")
for р in c.execute(
        "SELECT COALESCE(m.status,'письма нет') с, COUNT(*) n "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='edited' GROUP BY с ORDER BY n DESC"):
    print("  письмо %-16s %5d" % (р["с"], р["n"]))

print("\n=== ПРИМЕРЫ ===")
for р in c.execute(
        "SELECT cr.id, cr.created_at, cr.decided_at, cr.decided_by, r.email, "
        "       cr.subject, m.status mst FROM confirm_reviews cr "
        "  JOIN recipients r ON r.id=cr.recipient_id "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='edited' ORDER BY cr.id DESC LIMIT 8"):
    print("  #%-6s %s решил=%s | %-26s письмо=%s"
          % (р["id"], str(р["created_at"])[:16], str(р["decided_by"] or "-")[:18],
             str(р["email"])[:26], р["mst"]))
    print("        %s" % str(р["subject"])[:70])
