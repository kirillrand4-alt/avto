# -*- coding: utf-8 -*-
"""Только чтение: скольким из партии мы уже писали раньше."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

ряды = list(c.execute(
    "SELECT m.id, m.status, r.email, r.inn FROM messages m"
    " JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id=12"))
print("писем в партии: %d" % len(ряды))

было_почта = было_инн = 0
для = []
for р in ряды:
    if р["status"] in ("sent", "skipped"):
        continue
    n1 = c.execute("SELECT COUNT(*) FROM messages m2 JOIN recipients r2"
                   " ON r2.id=m2.recipient_id WHERE m2.status='sent'"
                   " AND m2.campaign_id<>12 AND r2.email=?", (р["email"],)).fetchone()[0]
    n2 = 0
    if р["inn"]:
        n2 = c.execute("SELECT COUNT(*) FROM messages m2 JOIN recipients r2"
                       " ON r2.id=m2.recipient_id WHERE m2.status='sent'"
                       " AND m2.campaign_id<>12 AND r2.inn=?", (р["inn"],)).fetchone()[0]
    if n1:
        было_почта += 1
    elif n2:
        было_инн += 1

print("\n=== СРЕДИ ЕЩЁ НЕ ОТПРАВЛЕННЫХ ===")
print("  этой же почте уже писали раньше: %d" % было_почта)
print("  этой компании (по ИНН) писали на другой адрес: %d" % было_инн)
print("  чистых, без прежних касаний: %d"
      % (sum(1 for р in ряды if р["status"] not in ("sent", "skipped"))
         - было_почта - было_инн))

print("\n=== ТЕКУЩИЙ СЧЁТ ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
