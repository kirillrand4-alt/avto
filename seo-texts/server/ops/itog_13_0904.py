# -*- coding: utf-8 -*-
"""Только чтение: итог по партии 13."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("=== РЕШЕНИЯ ===")
for р in c.execute("SELECT status, COUNT(*) k FROM confirm_reviews WHERE campaign_id=13"
                   " GROUP BY status ORDER BY k DESC"):
    print("  %-12s %d" % (р["status"], р["k"]))
print("\n=== ПИСЬМА ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " GROUP BY status"):
    print("  %-12s %d" % (р["status"], р["k"]))
print("  с телом: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                  " AND body_rendered<>''").fetchone()[0])
print("\n=== ПОЧЕМУ НЕ УШЛИ ОСТАЛЬНЫЕ ===")
for р in c.execute("SELECT last_error, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " AND status='skipped' GROUP BY last_error ORDER BY k DESC LIMIT 5"):
    print("  %3d | %s" % (р["k"], str(р["last_error"])[:80]))
ост = list(c.execute("SELECT email FROM confirm_reviews WHERE campaign_id=13"
                     " AND status='pending'"))
print("\n  остались в pending (%d):" % len(ост))
for р in ост:
    print("    %s" % р["email"])
