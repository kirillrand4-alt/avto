# -*- coding: utf-8 -*-
"""Последние отправленные письма кампании: poslednie_otpravlennye.py <campaign_id> [N=5]"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
for r in c.execute("SELECT id, sent_at, mailbox_id, subject FROM messages WHERE status='sent' AND campaign_id=? "
                   "ORDER BY sent_at DESC LIMIT ?", (int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 5)):
    print(r)
