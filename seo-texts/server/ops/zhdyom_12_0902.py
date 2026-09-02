# -*- coding: utf-8 -*-
"""Только чтение: ждём старта нашей партии."""
import datetime as dt
import sqlite3
import time

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for i in range(7):
    n12 = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                    " AND status='sent'").fetchone()[0]
    n11 = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=11"
                    " AND status='scheduled'").fetchone()[0]
    вс = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                   (dt.datetime.now().replace(hour=0, minute=0, second=0).isoformat(),)
                   ).fetchone()[0]
    print("%s | ушло всего %3d | кампания 11 в очереди %2d | НАША ПАРТИЯ ушло %d"
          % (dt.datetime.now().strftime("%H:%M:%S"), вс, n11, n12))
    if n12 > 0:
        break
    time.sleep(50)

print("\n=== ЕСЛИ ПАРТИЯ ПОШЛА ===")
for р in c.execute("SELECT mailbox_id, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " AND status='sent' GROUP BY mailbox_id ORDER BY k DESC"):
    print("  %-36s %d" % (р["mailbox_id"], р["k"]))
Я = "i.kuznetsova@sort-systems.ru"
п = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND status='sent'"
              " AND body_rendered LIKE '%Ирина Кузнецова%' AND mailbox_id<>?",
              (Я,)).fetchone()[0]
х = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12 AND status='sent'"
              " AND body_rendered LIKE '%Ирина Кузнецова%' AND mailbox_id=?",
              (Я,)).fetchone()[0]
print("  письма Ирины: с её ящика %d, с чужого %d (должно быть 0)" % (х, п))
