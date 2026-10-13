# -*- coding: utf-8 -*-
"""Ящик без IMAP-входа: шлёт ли он, когда последнее событие из него, что в конфиге."""
import sqlite3
import sys
ЯЩ = sys.argv[1] if len(sys.argv) > 1 else "a.kozlov@zernosort.ru"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
print("отправлено из ящика:", c.execute("SELECT count(*), max(sent_at) FROM messages WHERE mailbox_id=? AND status='sent'", (ЯЩ,)).fetchone())
print("в очереди (scheduled/sending/approved):", c.execute("SELECT status, count(*) FROM messages WHERE mailbox_id=? AND status IN ('scheduled','sending','approved','pending_review') GROUP BY 1", (ЯЩ,)).fetchall())
print("события из ящика по типам (последние):", c.execute("SELECT event_type, count(*), max(event_ts) FROM events WHERE mailbox_id=? GROUP BY 1", (ЯЩ,)).fetchall())
print("=== ЯЩИК ===")
