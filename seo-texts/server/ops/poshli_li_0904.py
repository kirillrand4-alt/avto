# -*- coding: utf-8 -*-
"""Только чтение: пошли ли письма после перезапуска."""
import datetime as dt
import sqlite3
import time

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
сут = utc.replace(hour=0, minute=0, second=0).isoformat()
н0 = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
               (сут,)).fetchone()[0]
print("до наблюдения отправлено сегодня: %d" % н0)
for i in range(6):
    time.sleep(60)
    n = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                  (сут,)).fetchone()[0]
    n13 = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                    " AND status='sent'").fetchone()[0]
    ск = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                   " AND status='skipped'").fetchone()[0]
    print("%s | сегодня %d | партия 13 ушло %d, снято %d"
          % (dt.datetime.now().strftime("%H:%M:%S"), n, n13, ск))
    if n13 >= 5:
        break
print("\n=== КТО ОТПРАВИЛ ПО ПАРТИИ 13 ===")
for р in c.execute("SELECT mailbox_id, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " AND status='sent' GROUP BY mailbox_id ORDER BY k DESC"):
    print("  %-36s %d" % (р["mailbox_id"], р["k"]))
