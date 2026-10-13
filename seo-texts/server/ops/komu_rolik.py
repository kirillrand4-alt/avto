# -*- coding: utf-8 -*-
"""Кому уходили письма со ссылкой на ролик: свод по дням и ящикам + список за последние N дней."""
import sqlite3
import sys
from collections import Counter
ролик, дней = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
строки = c.execute("SELECT m.id, m.sent_at, m.mailbox_id, r.company_name, r.email, r.region, r.inn FROM messages m "
                   "JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' AND m.body_rendered LIKE ? "
                   "ORDER BY m.sent_at DESC", ("%" + ролик + "%",)).fetchall()
print("всего отправлено писем с роликом: %d" % len(строки))
print("по дням: %s" % dict(sorted(Counter(str(р[1])[:10] for р in строки).items())[-8:]))
print("по ящикам: %s" % dict(Counter(р[2] for р in строки).most_common()))
свежие = c.execute("SELECT date('now', ?)", ("-%d days" % дней,)).fetchone()[0]
for р in строки:
    if str(р[1])[:10] >= свежие:
        print("   %s | %-32s | %-28s | %s | %s" % (str(р[1])[11:16], str(р[3])[:32], str(р[4])[:28], р[2].split("@")[0], str(р[5] or "")[:20]))
print("=== КОМУ РОЛИК ===")
