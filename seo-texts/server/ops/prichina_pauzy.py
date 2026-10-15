# -*- coding: utf-8 -*-
"""Причина паузы ящиков: prichina_pauzy.py <подстрока>"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
for r in c.execute("SELECT mailbox_id, paused, pause_reason, updated_at FROM mailbox_state WHERE mailbox_id LIKE ?", ("%" + sys.argv[1] + "%",)):
    print(r)
print("=== ПРИЧИНА ПАУЗЫ ===")
