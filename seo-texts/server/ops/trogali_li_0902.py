# -*- coding: utf-8 -*-
"""Только чтение: брал ли цикл наши письма в работу вообще."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("=== updated_at ПИСЕМ КАМПАНИИ 12 ===")
for р in c.execute("SELECT substr(updated_at,1,16) м, COUNT(*) k, MIN(attempt_count) а1,"
                   " MAX(attempt_count) а2 FROM messages WHERE campaign_id=12"
                   " GROUP BY м ORDER BY м"):
    print("  %-18s %4d писем, попыток %s..%s" % (р["м"], р["k"], р["а1"], р["а2"]))
print("  (срок ставили в 09:25; если updated_at там же и попыток 0 —")
print("   цикл до них ни разу не дошёл)")

print("\n=== ДЛЯ СРАВНЕНИЯ, КАМПАНИЯ 11 В ОЧЕРЕДИ ===")
for р in c.execute("SELECT substr(updated_at,1,16) м, COUNT(*) k FROM messages"
                   " WHERE campaign_id=11 AND status='scheduled'"
                   " GROUP BY м ORDER BY м DESC LIMIT 5"):
    print("  %-18s %4d" % (р["м"], р["k"]))
print("\n  claimed_at у наших: %s"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND claimed_at IS NOT NULL").fetchone()[0])
