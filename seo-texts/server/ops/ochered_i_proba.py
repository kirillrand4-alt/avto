# -*- coding: utf-8 -*-
"""Сколько адресов очереди ещё без вердикта пробы и как быстро он идёт."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

for ст in ("pending", "approved"):
    все = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status=?",
                    (ст,)).fetchone()[0]
    сполуч = c.execute("SELECT COUNT(*) FROM confirm_reviews cr JOIN recipients r "
                       "ON r.id=cr.recipient_id WHERE cr.status=?", (ст,)).fetchone()[0]
    безпробы = c.execute(
        "SELECT COUNT(*) FROM confirm_reviews cr JOIN recipients r "
        "  ON r.id=cr.recipient_id LEFT JOIN addr_probe p ON p.email=r.email "
        " WHERE cr.status=? AND p.email IS NULL", (ст,)).fetchone()[0]
    отработника = c.execute(
        "SELECT COUNT(*) FROM confirm_reviews cr JOIN recipients r "
        "  ON r.id=cr.recipient_id JOIN addr_probe p ON p.email=r.email "
        " WHERE cr.status=? AND p.source='проба'", (ст,)).fetchone()[0]
    print("%-9s всего %5d | с получателем %5d | без пробы %4d | от работника %5d"
          % (ст, все, сполуч, безпробы, отработника))

print("")
print("=== источники вердиктов ===")
for r in c.execute("SELECT COALESCE(source,'(пусто)') s, COUNT(*) n FROM addr_probe "
                   "GROUP BY s ORDER BY n DESC LIMIT 8"):
    print("   %-22s %d" % (r["s"], r["n"]))

print("")
print("=== проба за последние часы ===")
for r in c.execute("SELECT substr(ts,1,13) ч, COUNT(*) n FROM addr_probe "
                   " WHERE ts >= '2026-08-25' GROUP BY ч ORDER BY ч DESC LIMIT 10"):
    print("   %s  %d" % (r["ч"], r["n"]))
c.close()
