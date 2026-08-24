# -*- coding: utf-8 -*-
"""Что осталось в очереди после чистки: чем и когда сгенерировано."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("=== ОЧЕРЕДЬ ПО СТАТУСАМ ===")
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   " GROUP BY status ORDER BY n DESC"):
    print("  %-14s %5d" % (р["status"], р["n"]))

print("\n=== ЖИВЫЕ КАРТОЧКИ (pending+approved) ПО ДАТЕ СОЗДАНИЯ ===")
for р in c.execute(
        "SELECT substr(created_at,1,10) д, status, COUNT(*) n "
        "  FROM confirm_reviews WHERE status IN ('pending','approved') "
        " GROUP BY д, status ORDER BY д DESC, n DESC LIMIT 12"):
    print("  %s  %-10s %5d" % (р["д"], р["status"], р["n"]))

print("\n=== СНЯТО СЕГОДНЯ И КЕМ ===")
for р in c.execute(
        "SELECT COALESCE(decided_by,'-') кем, COUNT(*) n FROM confirm_reviews "
        " WHERE status='skipped' AND substr(COALESCE(decided_at,''),1,10)=date('now') "
        " GROUP BY кем ORDER BY n DESC LIMIT 8"):
    print("  %-36s %5d" % (str(р["кем"])[:36], р["n"]))

print("\n=== СКОЛЬКО ЖИВЫХ НАДО БУДЕТ ПРОГНАТЬ ЛИНЗОЙ ===")
н = c.execute("SELECT COUNT(*) n FROM confirm_reviews "
              " WHERE status IN ('pending','approved')").fetchone()["n"]
print("  карточек: %d" % н)
print("  по одной (как я гонял):  $%.1f" % (н * 0.019))
print("  пачками по восемь:       $%.1f" % (н * 0.0025))
