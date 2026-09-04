# -*- coding: utf-8 -*-
"""Только чтение: идёт ли отправка партии 13 сама."""
import datetime as dt
import sqlite3
import time

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
н0 = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
               " AND status='sent'").fetchone()[0]
print("на старте наблюдения ушло: %d" % н0)
for i in range(5):
    time.sleep(70)
    n = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                  " AND status='sent'").fetchone()[0]
    print("%s | партия 13 ушло %d (+%d)"
          % (dt.datetime.now().strftime("%H:%M:%S"), n, n - н0))
    if n > н0 + 3:
        break
итог = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                 " AND status='sent'").fetchone()[0]
print("\n=== ВЫВОД ===")
if итог > н0:
    print("  цикл панели работает сам: +%d писем за наблюдение" % (итог - н0))
else:
    print("  цикл панели НЕ шлёт: за пять минут ни одного письма")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
