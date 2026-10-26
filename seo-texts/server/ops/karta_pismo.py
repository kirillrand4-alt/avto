# -*- coding: utf-8 -*-
"""Карточка и её отправленное письмо: ящик, тема, In-Reply-To. karta_pismo.py <id>. Только чтение."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
к = c.execute("SELECT id, kind, status, email, subject, in_reply_to, message_id, decided_at FROM confirm_reviews WHERE id=?", (int(sys.argv[1]),)).fetchone()
print("карточка:", к)
if к and к[6]:
    print("письмо:", c.execute("SELECT id, status, mailbox_id, subject, in_reply_to, sent_at FROM messages WHERE id=?", (к[6],)).fetchone())
print("reply_sent:", c.execute("SELECT id, mailbox_id, event_ts, substr(detail_json,1,300) FROM events WHERE event_type='reply_sent' "
                              "AND detail_json LIKE ? ORDER BY id DESC LIMIT 1", ("%" + (к[3] if к else "") + "%",)).fetchone())
