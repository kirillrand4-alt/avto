# -*- coding: utf-8 -*-
"""Статус карточек и их писем: kartochka_status.py <id,id,...>"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
for i in sys.argv[1].split(","):
    print(c.execute("SELECT c.id, c.email, c.status, c.decided_by, m.status, m.mailbox_id, m.sent_at, m.last_error "
                    "FROM confirm_reviews c LEFT JOIN messages m ON m.id=c.message_id WHERE c.id=?", (int(i),)).fetchone())
