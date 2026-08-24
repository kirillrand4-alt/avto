# -*- coding: utf-8 -*-
"""Куда делись письма из очереди: было 343, стало 337.

Карточка уходит из pending только решением: одобрена, снята, отправлена,
правлена. Смотрим последние решения по времени и кем приняты.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("сейчас pending: %d"
      % c.execute("SELECT COUNT(*) n FROM confirm_reviews "
                  "WHERE status='pending'").fetchone()["n"])

print("\n=== ПОСЛЕДНИЕ 20 РЕШЕНИЙ ===")
for р in c.execute(
        "SELECT id, status, decided_at, COALESCE(decided_by,'-') кем, "
        "       substr(COALESCE(reason,''),1,52) причина "
        "  FROM confirm_reviews WHERE decided_at IS NOT NULL "
        " ORDER BY decided_at DESC LIMIT 20"):
    print("  %s #%-6s %-10s %-30s %s"
          % (str(р["decided_at"])[:19], р["id"], р["status"],
             str(р["кем"])[:30], р["причина"]))

print("\n=== РЕШЕНИЯ ЗА ПОСЛЕДНИЙ ЧАС ПО ВИДАМ ===")
for р in c.execute(
        "SELECT status, COALESCE(decided_by,'-') кем, COUNT(*) n "
        "  FROM confirm_reviews "
        " WHERE decided_at >= datetime('now','-60 minutes') "
        " GROUP BY status, кем ORDER BY n DESC"):
    print("  %-10s %-34s %d" % (р["status"], str(р["кем"])[:34], р["n"]))

print("\n=== ОТПРАВКА ЗА ПОСЛЕДНИЙ ЧАС ===")
for р in c.execute(
        "SELECT COUNT(*) n, MIN(sent_at) a, MAX(sent_at) b FROM messages "
        " WHERE status='sent' AND sent_at >= datetime('now','-60 minutes')"):
    print("  писем ушло: %d  (с %s по %s)"
          % (р["n"], str(р["a"] or "-")[:19], str(р["b"] or "-")[:19]))

print("\n=== ВКЛЮЧЕНА ЛИ АВТООТПРАВКА ===")
for р in c.execute("SELECT key, value FROM panel_settings "
                   " WHERE key LIKE '%auto%' OR key LIKE '%probe%'"):
    print("  %-30s = %s" % (р["key"], р["value"]))
