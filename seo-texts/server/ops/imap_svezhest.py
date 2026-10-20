# -*- coding: utf-8 -*-
"""Свежесть сбора входящих: таблицы про IMAP/опрос ящиков, последний опрос по
ящикам КЦ и Meyer, последние ответы. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
таб = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("таблицы:", [т for т in таб if any(w in т.lower() for w in ("imap", "poll", "inbox", "inbound", "mailbox", "reply", "thread"))])
for т in таб:
    if any(w in т.lower() for w in ("imap", "poll")):
        кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
        print("==", т, кол)
        for r in c.execute("SELECT * FROM %s ORDER BY rowid DESC LIMIT 6" % т):
            print("   ", tuple(str(x)[:40] for x in r))
print("последние ответы:")
for r in c.execute("SELECT event_ts, event_type, mailbox_id, campaign_id FROM events WHERE event_type IN ('reply','reply_auto') "
                   "ORDER BY event_ts DESC LIMIT 8"):
    print("   ", r)
