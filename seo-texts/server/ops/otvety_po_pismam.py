# -*- coding: utf-8 -*-
"""Наши ответы в тредах: с того же ящика, что и переписка?"""
import sqlite3
from collections import Counter
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
сч = Counter()
показано = 0
for r in c.execute(
        "SELECT m.id, m.recipient_id, m.mailbox_id, m.sent_at, rc.email "
        "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE m.in_reply_to IS NOT NULL AND m.status='sent' "
        " ORDER BY m.sent_at DESC LIMIT 60"):
    x = c.execute(
        "SELECT mailbox_id FROM messages WHERE recipient_id=? AND status='sent' "
        "   AND in_reply_to IS NULL ORDER BY sent_at ASC LIMIT 1",
        (r["recipient_id"],)).fetchone()
    исход = x[0] if x else None
    if not исход:
        сч["исходного письма не нашлось"] += 1
        continue
    if исход == r["mailbox_id"]:
        сч["ответ с ТОГО ЖЕ ящика"] += 1
    else:
        сч["ответ с ДРУГОГО ящика"] += 1
        if показано < 8:
            показано += 1
            print("   %-26s переписка %-30s ответ %s"
                  % (str(r["email"])[:26], str(исход)[:30], r["mailbox_id"]))
print("")
for к, n in сч.most_common():
    print("   %-34s %4d" % (к, n))
c.close()
