# -*- coding: utf-8 -*-
"""Входящие, пришедшие в окно простоя (event_ts), и когда записаны. Только чтение.
    vhodyashchie_dyra.py <с UTC> <по UTC>"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
р = c.execute("SELECT event_type, COUNT(*), MIN(created_at), MAX(created_at) FROM events "
              "WHERE event_type IN ('reply','reply_auto','other','bounce','dsn','complaint','reject_spam') "
              "AND event_ts BETWEEN ? AND ? GROUP BY event_type", (sys.argv[1], sys.argv[2])).fetchall()
print("пришло в окно %s..%s:" % (sys.argv[1], sys.argv[2]))
for r in р:
    print(" ", r)
