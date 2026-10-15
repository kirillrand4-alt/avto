# -*- coding: utf-8 -*-
"""Спам-отказы КЦ сегодня: кому, и отказывал ли этот домен получателя раньше (письмам Meyer)."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
for мб, mid in c.execute("SELECT mailbox_id, message_id FROM events WHERE event_type='reject_spam' AND event_ts>=date('now') "
                         "AND (mailbox_id LIKE '%compressor-%' OR mailbox_id LIKE '%kompressor-%')"):
    e = c.execute("SELECT r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.id=?", (mid,)).fetchone()
    дом = e[0].split("@")[1] if e else "?"
    раньше = c.execute("SELECT count(*) FROM events ev JOIN messages m ON m.id=ev.message_id JOIN recipients r ON r.id=m.recipient_id "
                       "WHERE ev.event_type='reject_spam' AND r.email LIKE ? AND ev.event_ts<date('now')", ("%@" + дом,)).fetchone()[0]
    ушло = c.execute("SELECT count(*) FROM events ev JOIN messages m ON m.id=ev.message_id JOIN recipients r ON r.id=m.recipient_id "
                     "WHERE ev.event_type='sent' AND r.email LIKE ?", ("%@" + дом,)).fetchone()[0]
    print("%-42s -> %-28s раньше отказов домену %d, писем туда ушло %d" % (мб, e[0] if e else "?", раньше, ушло))
print("=== СПАМ ПОЛУЧАТЕЛИ ===")
