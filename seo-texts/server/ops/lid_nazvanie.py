# -*- coding: utf-8 -*-
"""Переименовать компанию лида (и его получателя): lid_nazvanie.py LEAD_ID "Название" [--katit]"""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
лид, имя = int(sys.argv[1]), sys.argv[2]
r = c.execute("SELECT company_name, recipient_id FROM leads WHERE id=?", (лид,)).fetchone(); print("было:", r)
if "--katit" in sys.argv:
    c.execute("UPDATE leads SET company_name=? WHERE id=?", (имя, лид))
    if r and r[1] and "--tolko-lid" not in sys.argv: c.execute("UPDATE recipients SET company_name=? WHERE id=?", (имя, r[1]))
    c.commit(); print("стало:", имя)
