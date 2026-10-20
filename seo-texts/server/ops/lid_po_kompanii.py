# -*- coding: utf-8 -*-
"""Лиды компании по ИНН/названию: lid_po_kompanii.py <кусок>..."""
import sqlite3
import sys
c = sqlite3.connect(r"C:\sender\sender.db")
for к in sys.argv[1:]:
    л = "%" + к + "%"
    print("==", к)
    for r in c.execute("SELECT id, email, company_name, inn, status, reply_kind, created_at FROM leads WHERE company_name LIKE ? OR inn LIKE ? OR email LIKE ?", (л, л, л)):
        print("   ", r)
