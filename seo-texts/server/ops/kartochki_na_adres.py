# -*- coding: utf-8 -*-
"""Карточки подтверждения на адрес за сегодня (все виды): kartochki_na_adres.py АДРЕС. Только чтение."""
import json, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
for r in c.execute("SELECT id, status, kind, created_at, json_extract(panel_json,'$.mailbox_id'), COALESCE(reason,'') FROM confirm_reviews "
                   "WHERE lower(email)=lower(?) AND created_at >= date('now') ORDER BY id", (sys.argv[1],)):
    print(r)
