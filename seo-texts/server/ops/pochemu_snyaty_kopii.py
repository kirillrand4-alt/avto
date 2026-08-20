# -*- coding: utf-8 -*-
"""Почему цикл снял письма копий: причина в last_error."""
import sqlite3

ИДЫ = (3811, 3812, 3813, 3814, 3815, 3816, 3817, 3818)
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for r in c.execute("SELECT id, status, substr(updated_at,1,19) upd, "
                   "COALESCE(last_error,'') err FROM messages WHERE id IN "
                   + str(ИДЫ)):
    print(f"  письмо {r['id']} {r['status']:<10} {r['upd']}  {r['err'][:90]}")
