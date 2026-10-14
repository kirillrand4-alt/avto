# -*- coding: utf-8 -*-
"""Куда делись письма, отправленные кнопкой в автоотправку за последние N часов:
статусы messages и причины (last_error). Только чтение.

    kuda_delis_avto.py [chasov=12]
"""
import sqlite3
import sys

Ч = int(dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а).get("chasov", "12"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
окно = "-%d hours" % Ч
print("одобрено кнопкой за %d ч: %s" % (Ч, c.execute(
    "SELECT count(*) FROM confirm_reviews WHERE reason='bulk-to-auto' AND decided_at >= datetime('now', ?)",
    (окно,)).fetchone()[0]))
print("статусы их писем:")
for st, n in c.execute(
        "SELECT m.status, count(*) FROM confirm_reviews r JOIN messages m ON m.id=r.message_id "
        "WHERE r.reason='bulk-to-auto' AND r.decided_at >= datetime('now', ?) GROUP BY 1 ORDER BY 2 DESC", (окно,)):
    print("   %-14s %d" % (st, n))
print("причины не-scheduled/не-sent:")
for st, ош, n in c.execute(
        "SELECT m.status, substr(coalesce(m.last_error,''),1,110), count(*) FROM confirm_reviews r "
        "JOIN messages m ON m.id=r.message_id WHERE r.reason='bulk-to-auto' AND r.decided_at >= datetime('now', ?) "
        "AND m.status NOT IN ('scheduled','sent') GROUP BY 1,2 ORDER BY 3 DESC LIMIT 15", (окно,)):
    print("   %-10s %4d  %s" % (st, n, ош))
print("=== КУДА ДЕЛИСЬ ===")
