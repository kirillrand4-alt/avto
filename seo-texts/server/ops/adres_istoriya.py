# -*- coding: utf-8 -*-
"""Вся история адреса в sender.db (владелец 22.10: «была ли проба? 2 раза
попытка на 1 адрес?»): проба, отправки, карточки, события. Только чтение.
    adres_istoriya.py <email,email,...>"""
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
таб = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
for em in sys.argv[1].lower().split(","):
    print("\n=====", em)
    for т in таб:
        кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
        поле = next((k for k in ("email", "value", "to_email", "recipient_email", "address") if k in кол), None)
        if поле:
            ряды = c.execute("SELECT * FROM %s WHERE lower(%s)=? LIMIT 12" % (т, поле), (em,)).fetchall()
        elif "detail" in кол or "details" in кол:
            д = "detail" if "detail" in кол else "details"
            ряды = c.execute("SELECT * FROM %s WHERE lower(%s) LIKE ? ORDER BY rowid DESC LIMIT 8" % (т, д), ("%" + em + "%",)).fetchall()
        else:
            continue
        for r in ряды:
            print("[%s] %s" % (т, " | ".join("%s=%s" % (k, str(v)[:90]) for k, v in zip(кол, r) if v not in (None, ""))))
    рид = [r[0] for r in c.execute("SELECT id FROM recipients WHERE lower(email)=?", (em,))]
    for rid in рид:
        for r in c.execute("SELECT id, campaign_id, status, mailbox_id, sent_at, last_error FROM messages WHERE recipient_id=?", (rid,)):
            print("[messages]", r)
