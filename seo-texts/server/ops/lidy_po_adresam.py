# -*- coding: utf-8 -*-
"""Есть ли лид по адресу/домену: lidy_po_adresam.py <домен> [<домен>...]"""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
for д in sys.argv[1:]:
    р = c.execute("SELECT id, email, status, reply_kind, substr(created_at,1,16) FROM leads WHERE email LIKE ? ORDER BY id DESC LIMIT 3", ("%" + д,)).fetchall()
    print(д, "->", р or "ЛИДА НЕТ")
print("=== ЛИДЫ ===")
