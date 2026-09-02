# -*- coding: utf-8 -*-
"""Только чтение: ждём открытия окна 09:00 и смотрим, пошли ли письма."""
import datetime as dt
import sqlite3
import time

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row


def снимок():
    у = dt.datetime.now().replace(hour=0, minute=0, second=0).isoformat()
    n = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent'"
                  " AND sent_at>=?", (у,)).fetchone()[0]
    сг = c.execute("SELECT COUNT(*) FROM messages WHERE status='sending'").fetchone()[0]
    ск = c.execute("SELECT COUNT(*) FROM messages WHERE status='skipped'"
                   " AND updated_at>=?", (у,)).fetchone()[0]
    return n, сг, ск


н0 = снимок()
print("до окна (%s): отправлено сегодня %d, в работе %d, скипов сегодня %d"
      % (dt.datetime.now().strftime("%H:%M"), *н0))

цель = dt.datetime.now().replace(hour=9, minute=4, second=0)
пока = (цель - dt.datetime.now()).total_seconds()
if пока > 0:
    print("ждём открытия окна: %d сек" % int(пока))
    time.sleep(min(пока, 700))

for i in range(5):
    time.sleep(45)
    n, сг, ск = снимок()
    print("%s | отправлено сегодня %d | в работе %d | скипов %d"
          % (dt.datetime.now().strftime("%H:%M:%S"), n, сг, ск))
    if n > н0[0]:
        break

print("\n=== ИТОГ ===")
n, сг, ск = снимок()
if n > н0[0]:
    print("  ЦИКЛ ЖИВ: письма пошли (%d за сегодня)" % n)
    for р in c.execute("SELECT sent_at, mailbox_id, campaign_id FROM messages"
                       " WHERE status='sent' ORDER BY sent_at DESC LIMIT 5"):
        print("    %s | %s | кампания %s"
              % (str(р["sent_at"])[11:19], р["mailbox_id"], р["campaign_id"]))
else:
    print("  ЦИКЛ НЕ ШЛЁТ: окно открыто, письма созрели, отправок нет")
