# -*- coding: utf-8 -*-
"""«В отправке» и «просрочено» с панели: что за письма. Только чтение."""
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
print("сейчас UTC:", c.execute("SELECT strftime('%Y-%m-%dT%H:%M','now')").fetchone()[0])
print("== в отправке (sending):")
for r in c.execute("SELECT m.id, m.campaign_id, m.claimed_at, r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sending' ORDER BY m.claimed_at"):
    print("  ", r[0], кам.get(r[1]), r[2][:16], r[3])
ОДОБР = "(SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')"
ряды = c.execute("SELECT m.id, m.campaign_id, m.scheduled_at, coalesce(m.last_error,''), m.attempt_count, r.email, r.tz FROM messages m "
                 "JOIN recipients r ON r.id=m.recipient_id WHERE m.status='scheduled' AND m.scheduled_at < datetime('now','-1 hour') AND %s "
                 "ORDER BY m.scheduled_at" % ОДОБР).fetchall()
print("== одобренные scheduled с временем старше часа:", len(ряды), Counter(кам.get(r[1]) for r in ряды))
print("   причины:", Counter(r[3][:60] for r in ряды).most_common(6))
for r in ряды[:25]:
    print("  ", r[0], кам.get(r[1]), r[2][:16], "попыток", r[4], r[5], r[6], "|", r[3][:70])
