# -*- coding: utf-8 -*-
"""Письма КЦ, отвергнутые Яндексом «подозрение на спам», и ушедшие — тема, текст, ящик, кому."""
import json
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
кц = [mb.mailbox_id for mb in cfg.mailboxes() if mb.division == "kc"]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for тип in ("reject_spam", "sent"):
    print("########", тип)
    for е in c.execute("SELECT message_id, mailbox_id, event_ts FROM events WHERE event_type=? AND event_ts>=date('now') "
                       "AND mailbox_id IN (%s) ORDER BY id LIMIT 4" % ",".join("?" * len(кц)), [тип] + кц):
        м = c.execute("SELECT m.subject, m.body_rendered, r.email FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                      "WHERE m.id=?", (е["message_id"],)).fetchone()
        if not м:
            continue
        print("== %s -> %s %s\nТема: %s\n%s\n" % (е["mailbox_id"], м["email"], е["event_ts"][:16], м["subject"], (м["body_rendered"] or "")[:2500]))
print("=== СПАМ КЦ ===")
