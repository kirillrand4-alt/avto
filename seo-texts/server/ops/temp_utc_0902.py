# -*- coding: utf-8 -*-
"""Только чтение: честный темп отправки, время сверяем в UTC."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
мск = dt.datetime.now()
print("сейчас: %s МСК (%s UTC)" % (мск.strftime("%H:%M:%S"), utc.strftime("%H:%M:%S")))

утро = utc.replace(hour=0, minute=0, second=0).isoformat()
n = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
              (утро,)).fetchone()[0]
print("\n=== ТЕМП ===")
for мин in (5, 15, 30, 60):
    п = (utc - dt.timedelta(minutes=мин)).isoformat()
    k = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                  (п,)).fetchone()[0]
    print("  за %2d мин: %3d писем (%.1f/мин)" % (мин, k, k / float(мин)))
print("  за сегодня: %d" % n)

до14 = (мск.replace(hour=14, minute=0, second=0) - мск).total_seconds() / 60
п15 = (utc - dt.timedelta(minutes=15)).isoformat()
k15 = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                (п15,)).fetchone()[0]
осталось = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                     " AND status='scheduled'").fetchone()[0]
темп = k15 / 15.0
print("\n=== ПРОГНОЗ ===")
print("  до 14:00 осталось %d мин" % до14)
print("  нашей партии осталось %d писем" % осталось)
if темп > 0:
    print("  при темпе %.1f/мин партия закончится примерно через %d мин"
          % (темп, int(осталось / темп)))
    print("  успеет до 14:00: %s" % ("да" if осталось / темп < до14 else "НЕТ"))

print("\n=== ЧТО В ОЧЕРЕДИ (те самые 547) ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages"
                   " WHERE status IN ('scheduled','pending_review','sending')"
                   " GROUP BY status ORDER BY k DESC"):
    п = {"scheduled": "одобрено, уйдёт само",
         "pending_review": "ЖДЁТ ВАШЕГО РЕШЕНИЯ в панели",
         "sending": "в работе прямо сейчас"}.get(р["status"], "")
    print("  %-16s %4d  %s" % (р["status"], р["k"], п))

print("\n=== НАША ПАРТИЯ ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
