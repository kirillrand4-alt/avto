# -*- coding: utf-8 -*-
"""Только чтение: текущий счёт партии 13 и причины снятия."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("сейчас %s МСК" % dt.datetime.now().strftime("%H:%M:%S"))
print("\n=== ПАРТИЯ 13 ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " GROUP BY status ORDER BY k DESC"):
    print("  %-14s %d" % (р["status"], р["k"]))
print("  решений pending: %d"
      % c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                  " AND status='pending'").fetchone()[0])

print("\n=== ПРИЧИНЫ СНЯТИЯ ===")
for р in c.execute("SELECT last_error, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " AND status='skipped' GROUP BY last_error ORDER BY k DESC"):
    print("  %3d | %s" % (р["k"], str(р["last_error"])[:84]))

print("\n=== КОГО СНЯЛИ ===")
for р in c.execute("SELECT r.email, r.company_name, m.last_error FROM messages m"
                   " JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.campaign_id=13 AND m.status='skipped' LIMIT 14"):
    print("  %-34s %-24s %s" % (р["email"][:34], str(р["company_name"])[:24],
                                str(р["last_error"])[:40]))

print("\n=== ТЕМП ЗА ЧАС (время в UTC) ===")
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
for мин in (10, 30, 60):
    п = (utc - dt.timedelta(minutes=мин)).isoformat()
    k = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                  " AND status='sent' AND sent_at>=?", (п,)).fetchone()[0]
    print("  за %2d мин: %3d писем" % (мин, k))
