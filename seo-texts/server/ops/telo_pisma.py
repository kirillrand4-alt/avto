# -*- coding: utf-8 -*-
"""Тело письма по id сообщения: telo_pisma.py <id>. Только чтение."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
r = c.execute("SELECT subject, body_rendered FROM messages WHERE id=?", (int(sys.argv[1]),)).fetchone()
print(r[0]); print(r[1])
