# -*- coding: utf-8 -*-
"""Только чтение: пошла ли наша партия и с правильных ли ящиков."""
import datetime as dt
import sqlite3
import time

Я = "i.kuznetsova@sort-systems.ru"
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

for круг in range(6):
    if круг:
        time.sleep(60)
    n = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND status='sent'").fetchone()[0]
    ск = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                   " AND status='skipped'").fetchone()[0]
    print("%s | кампания 12: ушло %d, скипов %d"
          % (dt.datetime.now().strftime("%H:%M:%S"), n, ск))
    if n >= 6:
        break

print("\n=== КТО ЧТО ОТПРАВИЛ ПО КАМПАНИИ 12 ===")
for р in c.execute("SELECT mailbox_id, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " AND status='sent' GROUP BY mailbox_id ORDER BY k DESC"):
    print("  %-36s %d" % (р["mailbox_id"], р["k"]))

print("\n=== ГЛАВНАЯ ПРОВЕРКА: ПИСЬМА ИРИНЫ ===")
плохо = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND status='sent' AND body_rendered LIKE '%Ирина Кузнецова%'"
                  " AND mailbox_id<>?", (Я,)).fetchone()[0]
хорошо = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                   " AND status='sent' AND body_rendered LIKE '%Ирина Кузнецова%'"
                   " AND mailbox_id=?", (Я,)).fetchone()[0]
print("  ушло от её имени с ЕЁ ящика: %d" % хорошо)
print("  ушло от её имени с ЧУЖОГО ящика: %d (должно быть 0)" % плохо)

print("\n=== СКИПЫ ПО НАШЕЙ ПАРТИИ ===")
for р in c.execute("SELECT last_error, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " AND status='skipped' GROUP BY last_error ORDER BY k DESC LIMIT 5"):
    print("  %-62s %d" % (str(р["last_error"])[:62], р["k"]))

print("\n=== ОСТАТОК ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
