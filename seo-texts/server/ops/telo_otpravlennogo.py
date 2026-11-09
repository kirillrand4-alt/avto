# -*- coding: utf-8 -*-
"""Тело отправленного письма (body_rendered) по messages.id: telo_otpravlennogo.py ID [хвост_знаков]. Только чтение."""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
r = c.execute("SELECT mailbox_id, subject, body_rendered FROM messages WHERE id=?", (int(sys.argv[1]),)).fetchone()
n = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
print(r[0], "|", r[1]); print((r[2] or "")[-n:])
