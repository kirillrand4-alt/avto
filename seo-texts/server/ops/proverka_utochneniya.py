# -*- coding: utf-8 -*-
"""Что с письмами на два адреса после уточнения 19.11: все messages, карточки и send_log. Только чтение."""
import sqlite3
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
for em in ("i.andreev@termotronic.ru", "e.chernyshov@elastomeric.ru"):
    print("==", em)
    for r in к.execute("SELECT m.id, m.status, m.sent_at, m.mailbox_id, m.idempotency_key FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email)=? ORDER BY m.id", (em,)): print("  письмо", r)
    for r in к.execute("SELECT id, status, message_id, substr(coalesce(edited_body, body),1,60), updated_at FROM confirm_reviews WHERE lower(email)=? ORDER BY id", (em,)): print("  карточка", r)
    for r in к.execute("SELECT * FROM send_log WHERE lower(email)=? ORDER BY ts", (em,)): print("  send_log", r)
