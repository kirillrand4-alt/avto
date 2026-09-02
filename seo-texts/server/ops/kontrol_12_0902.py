# -*- coding: utf-8 -*-
"""Только чтение: пошли ли письма и не тронута ли кампания 12."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
у = dt.datetime.now().replace(hour=0, minute=0, second=0).isoformat()

print("время панели: %s" % dt.datetime.now().strftime("%H:%M:%S"))
print("\n=== КАМПАНИЯ 12 (наша) ===")
for р in c.execute("SELECT status, COUNT(*) n FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["n"]))
for р in c.execute("SELECT DISTINCT scheduled_at FROM messages WHERE campaign_id=12"):
    print("  срок: %s" % р["scheduled_at"])
ушло12 = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                   " AND status='sent'").fetchone()[0]
print("  УШЛО ИЗ НАШЕЙ ПАРТИИ: %d (должно быть 0)" % ушло12)

print("\n=== ОТПРАВКА СЕГОДНЯ ===")
n = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
              (у,)).fetchone()[0]
print("  всего: %d" % n)
for р in c.execute("SELECT campaign_id, COUNT(*) k FROM messages WHERE status='sent'"
                   " AND sent_at>=? GROUP BY campaign_id", (у,)):
    print("  кампания %s: %d" % (р["campaign_id"], р["k"]))
print("  по ящикам:")
for р in c.execute("SELECT mailbox_id, COUNT(*) k FROM messages WHERE status='sent'"
                   " AND sent_at>=? GROUP BY mailbox_id ORDER BY k DESC", (у,)):
    print("    %-36s %d" % (р["mailbox_id"], р["k"]))

print("\n=== СКИПЫ СЕГОДНЯ ===")
ск = list(c.execute("SELECT last_error, COUNT(*) k FROM messages WHERE status='skipped'"
                    " AND updated_at>=? GROUP BY last_error ORDER BY k DESC LIMIT 6",
                    (у,)))
print("  всего: %d" % sum(р["k"] for р in ск))
for р in ск:
    print("    %-60s %d" % (str(р["last_error"])[:60], р["k"]))
print("  из них по направлению: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='skipped'"
                  " AND updated_at>=? AND last_error LIKE '%division%'",
                  (у,)).fetchone()[0])

print("\n=== ОСТАЛОСЬ В ОЧЕРЕДИ ===")
сейчас = dt.datetime.now().isoformat()
print("  созревших одобренных: %d"
      % c.execute("SELECT COUNT(*) FROM messages m WHERE m.status='scheduled'"
                  " AND m.scheduled_at<=? AND EXISTS (SELECT 1 FROM confirm_reviews cr"
                  " WHERE cr.message_id=m.id AND cr.status IN ('approved','edited'))",
                  (сейчас,)).fetchone()[0])
