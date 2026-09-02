# -*- coding: utf-8 -*-
"""Только чтение: нормально ли идёт отправка и что за 547 в очереди."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
у = сейчас.replace(hour=0, minute=0, second=0).isoformat()

print("время %s, окно до 14:00" % сейчас.strftime("%H:%M"))
n = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
              (у,)).fetchone()[0]
откр = сейчас.replace(hour=9, minute=0, second=0)
мин = max(1.0, (сейчас - откр).total_seconds() / 60.0)
print("отправлено сегодня: %d, темп %.1f писем/мин" % (n, n / мин))
print("до 14:00 при этом темпе успеет ещё примерно %d"
      % int((сейчас.replace(hour=14, minute=0) - сейчас).total_seconds() / 60 * (n / мин)))

print("\n=== ЧТО ИМЕННО В ОЧЕРЕДИ ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages"
                   " WHERE status IN ('scheduled','pending_review','sending')"
                   " GROUP BY status ORDER BY k DESC"):
    print("  %-16s %4d" % (р["status"], р["k"]))
print("  scheduled = одобрено, ждёт отправки")
print("  pending_review = ждёт ВАШЕГО решения в панели, само не уйдёт")

print("\n=== ПО КАМПАНИЯМ ===")
for р in c.execute("SELECT m.campaign_id, c.name, m.status, COUNT(*) k FROM messages m"
                   " LEFT JOIN campaigns c ON c.id=m.campaign_id"
                   " WHERE m.status IN ('scheduled','pending_review','sending')"
                   " GROUP BY m.campaign_id, m.status ORDER BY m.campaign_id"):
    print("  #%-3s %-24s %-15s %4d" % (р["campaign_id"], str(р["name"])[:24],
                                       р["status"], р["k"]))

print("\n=== НАША ПАРТИЯ ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
Я = "i.kuznetsova@sort-systems.ru"
print("  письма Ирины: с её ящика %d, с чужого %d"
      % (c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND"
                   " status='sent' AND body_rendered LIKE '%Ирина Кузнецова%'"
                   " AND mailbox_id=?", (Я,)).fetchone()[0],
         c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND"
                   " status='sent' AND body_rendered LIKE '%Ирина Кузнецова%'"
                   " AND mailbox_id<>?", (Я,)).fetchone()[0]))

print("\n=== ОТПРАВКИ ПО ЯЩИКАМ ЗА СЕГОДНЯ ===")
for р in c.execute("SELECT mailbox_id, COUNT(*) k FROM messages WHERE status='sent'"
                   " AND sent_at>=? GROUP BY mailbox_id ORDER BY k DESC LIMIT 12",
                   (у,)):
    print("  %-36s %d" % (р["mailbox_id"], р["k"]))

print("\n=== ОШИБКИ ЗА СЕГОДНЯ ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE updated_at>=?"
                   " AND status IN ('failed','skipped') GROUP BY status", (у,)):
    print("  %-10s %d" % (р["status"], р["k"]))
