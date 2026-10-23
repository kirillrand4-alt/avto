# -*- coding: utf-8 -*-
"""Лиды и наши ответы по получателю: lid_po_rid.py <rid>. Только чтение."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
rid = int(sys.argv[1])
for r in c.execute("SELECT id, status, reply_kind, phone, substr(need,1,160), created_at FROM leads WHERE recipient_id=?", (rid,)):
    print("лид", r)
for r in c.execute("SELECT id, event_type, event_ts, mailbox_id FROM events WHERE recipient_id=? AND event_type IN ('reply','reply_auto','reply_sent') ORDER BY id", (rid,)):
    print("событие", r)
for r in c.execute("SELECT id, kind, status, created_at FROM confirm_reviews WHERE recipient_id=? AND kind='reply'", (rid,)):
    print("карточка ответа", r)
