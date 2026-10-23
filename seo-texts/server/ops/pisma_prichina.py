# -*- coding: utf-8 -*-
"""Статус и причина по письмам: pisma_prichina.py id,id,... Только чтение."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for i in sys.argv[1].split(","):
    print(c.execute("SELECT id, status, substr(updated_at,1,16), last_error FROM messages WHERE id=?", (int(i),)).fetchone())
    print("  карточка:", c.execute("SELECT id, status, reason FROM confirm_reviews WHERE message_id=?", (int(i),)).fetchall())
