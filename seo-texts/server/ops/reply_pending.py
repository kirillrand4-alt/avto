# -*- coding: utf-8 -*-
"""Карточки подтверждения по ИНН (все статусы): reply_pending.py ИНН [ИНН…]. Только чтение."""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
for inn in sys.argv[1:]:
    print("== ИНН", inn)
    for r in c.execute("SELECT id, status, kind, email, substr(created_at,1,16), COALESCE(reason,''), subject, substr(body,1,300) FROM confirm_reviews WHERE inn=? ORDER BY id", (inn,)):
        print(r[:7]); print("    ", (r[7] or "").replace("\n", " / "))
