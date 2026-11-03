# -*- coding: utf-8 -*-
"""Статус карточек и след отправки: kartochka_status.py ID [ID…]"""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for i in sys.argv[1:]:
    print(c.execute("SELECT id, status, decided_at, email, subject, reason FROM confirm_reviews WHERE id=?", (int(i),)).fetchone())
cols = [r[1] for r in c.execute("PRAGMA table_info(events)")]
print(cols)
