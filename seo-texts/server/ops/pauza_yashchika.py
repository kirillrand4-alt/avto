# -*- coding: utf-8 -*-
"""Пауза одного ящика: pauza_yashchika.py <ящик> <причина>"""
import sqlite3
import sys
import time
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
with c:
    n = c.execute("UPDATE mailbox_state SET paused=1, pause_reason=?, updated_at=? WHERE mailbox_id=?",
                  (" ".join(sys.argv[2:]), time.strftime("%Y-%m-%dT%H:%M:%S"), sys.argv[1])).rowcount
print("на паузе: %s (%d)" % (sys.argv[1], n))
print("=== ПАУЗА ЯЩИКА ===")
