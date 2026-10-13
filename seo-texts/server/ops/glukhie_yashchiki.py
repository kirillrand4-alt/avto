# -*- coding: utf-8 -*-
"""Какие ящики «оглохли»: шлют, а входящих событий (reply/other/bounce/auto) давно нет."""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
print("%-40s %-17s %-17s %s" % ("ящик", "посл. отправка", "посл. входящее", "отправлено с 01.10"))
for mb in cfg.mailboxes():
    я = mb.mailbox_id
    отп = c.execute("SELECT max(sent_at), sum(sent_at >= '2026-10-01') FROM messages WHERE mailbox_id=? AND status='sent'", (я,)).fetchone()
    вх = c.execute("SELECT max(event_ts) FROM events WHERE mailbox_id=? AND event_type IN "
                   "('reply','other','bounce','reply_auto','reject_spam','complaint','dsn','unsubscribe')", (я,)).fetchone()[0]
    print("%-40s %-17s %-17s %s" % (я[:40], str(отп[0])[:16], str(вх)[:16], отп[1] or 0))
print("=== ГЛУХИЕ ЯЩИКИ ===")
