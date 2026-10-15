# -*- coding: utf-8 -*-
"""Письма в расписании/отправке с не-ASCII адресом (SMTP падает UnicodeEncodeError
на каждом цикле автоотправки). --snyat: перевести их в skipped с причиной."""
import sqlite3
import sys
import time
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
ряды = [(m, e, st) for m, e, st in c.execute(
    "SELECT m.id, r.email, m.status FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "WHERE m.status IN ('scheduled','sending','approved')") if not str(e or "").isascii()]
for р in ряды:
    print(р)
if "--idna" in sys.argv and ряды:
    # домен .рф в punycode: SMTP его принимает, письмо уходит как есть
    with c:
        for m, e, st in ряды:
            лок, дом = e.split("@", 1)
            if лок.isascii():
                нов = лок + "@" + дом.encode("idna").decode()
                c.execute("UPDATE recipients SET email=? WHERE lower(email)=lower(?)", (нов, e))
                print("  %s -> %s" % (e, нов))
if "--snyat" in sys.argv and ряды:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        for m, e, st in ряды:
            c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=?",
                      ("адрес не-ASCII: SMTP не принимает (UnicodeEncodeError)", т, m))
    print("снято: %d" % len(ряды))
print("=== НЕ-ASCII АДРЕСА: %d ===" % len(ряды))
